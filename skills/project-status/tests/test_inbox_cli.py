"""Tests for inbox.py. Run: python3 -m unittest discover -s skills/project-status/tests"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
_loader = importlib.machinery.SourceFileLoader("ps_inbox", str(HERE.parent / "inbox.py"))
_spec = importlib.util.spec_from_loader("ps_inbox", _loader)
IB = importlib.util.module_from_spec(_spec)
_loader.exec_module(IB)

T0 = datetime(2026, 1, 14, 18, 0, tzinfo=timezone.utc)


class InboxCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.now = T0

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(IB, "NOW", lambda: self.now), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = IB.main(["--home", str(self.home), *argv])
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def data(self):
        return json.loads((self.home / "inbox.json").read_text())

    def item(self, item_id):
        return next(i for i in self.data()["items"] if i["id"] == item_id)

    def test_add_creates_file(self):
        code, out, _ = self.run_cli("add", "--kind", "todo", "--title", "Book travel", "--id", "t1", "--effort", "1h 10m", "--who", "Sam")
        self.assertEqual(code, 0)
        it = self.item("t1")
        self.assertEqual((it["kind"], it["effort_min"], it["who_waits"], it["origin"]), ("todo", 70, "Sam", "session"))
        self.assertEqual(it["since"], "2026-01-14T18:00:00Z")
        self.assertFalse((self.home / "inbox.json.tmp").exists())

    def test_ref_is_the_id(self):
        self.run_cli("add", "--kind", "ask", "--title", "x", "--ref", "gh:acme/billing#5")
        self.assertEqual(self.data()["items"][0]["id"], "gh:acme/billing#5")

    def test_url_ref_is_stored_canonical(self):
        self.run_cli("add", "--kind", "ask", "--title", "x", "--ref", "https://github.com/acme/billing/pull/5/files")
        it = self.data()["items"][0]
        self.assertEqual((it["id"], it["ref"]), ("gh:acme/billing#5", "gh:acme/billing#5"))

    def test_lock_file_is_used(self):
        with mock.patch.object(IB.fcntl, "flock") as fl:
            self.run_cli("add", "--kind", "todo", "--title", "x", "--id", "t1")
        self.assertEqual(fl.call_args[0][1], IB.fcntl.LOCK_EX)
        self.assertTrue((self.home / "inbox.json.lock").exists())

    def test_slug_id_without_id_or_ref(self):
        self.run_cli("add", "--kind", "todo", "--title", "Renew the badge!")
        self.assertRegex(self.data()["items"][0]["id"], r"^renew-the-badge-[0-9a-f]{6}$")

    def test_readd_updates_keeps_since_and_snooze_clears_done(self):
        self.run_cli("add", "--kind", "todo", "--title", "Old", "--id", "t1", "--since", "2026-01-01T00:00:00Z")
        self.run_cli("snooze", "t1", "--until", "2026-01-20")
        self.run_cli("done", "t1")
        self.now = T0 + timedelta(hours=1)
        self.run_cli("add", "--kind", "todo", "--title", "New words", "--id", "t1")
        it = self.item("t1")
        self.assertEqual((it["title"], it["since"], it["snooze_until"], it["done_at"]),
                         ("New words", "2026-01-01T00:00:00Z", "2026-01-20", None))

    def test_done_by_id_and_by_text(self):
        self.run_cli("add", "--kind", "todo", "--title", "Book travel", "--id", "t1")
        self.run_cli("add", "--kind", "todo", "--title", "Renew badge", "--id", "t2")
        self.assertEqual(self.run_cli("done", "t1")[0], 0)
        self.assertEqual(self.run_cli("done", "BADGE")[0], 0)
        self.assertTrue(all(i["done_at"] for i in self.data()["items"]))

    def test_no_match_exits_1(self):
        code, _, err = self.run_cli("done", "nothing")
        self.assertEqual(code, 1)
        self.assertIn("no inbox item", err)

    def test_snooze_on_a_derived_id_is_refused(self):
        self.run_cli("add", "--kind", "todo", "--title", "x", "--id", "t1")
        code, _, err = self.run_cli("snooze", "gh:acme/billing#5", "--until", "2026-01-20")
        self.assertEqual(code, 1)
        self.assertIn("only session items", err)

    def test_sync_upserts_and_closes_missing_board_items_only(self):
        self.run_cli("add", "--kind", "todo", "--title", "Mine", "--id", "s1")
        self.run_cli("add", "--kind", "send-draft", "--title", "Old draft", "--id", "b-old", "--origin", "board")
        f = self.home / "items.json"
        f.write_text(json.dumps([
            {"id": "b1", "kind": "approve-agent", "title": "Approve agent", "effort": "2m"},
            {"id": "b2", "kind": "confirm", "title": "Confirm delivery", "since": "2026-01-08T00:00:00Z", "due": "2026-01-15",
             "project": "billing-migration", "who": "Ana"},
        ]))
        code, out, _ = self.run_cli("sync", "--origin", "board", "--file", str(f))
        self.assertEqual(code, 0)
        self.assertIn("1 marked done", out)
        self.assertIsNone(self.item("s1")["done_at"])
        self.assertIsNotNone(self.item("b-old")["done_at"])
        b2 = self.item("b2")
        self.assertEqual((b2["origin"], b2["since"], b2["project_id"], b2["who_waits"]), ("board", "2026-01-08T00:00:00Z", "billing-migration", "Ana"))
        self.assertEqual(self.item("b1")["effort_min"], 2)

    def test_sync_reupsert_without_since_keeps_since_and_snooze(self):
        f = self.home / "items.json"
        f.write_text(json.dumps([{"id": "b1", "kind": "todo", "title": "T", "since": "2026-01-02T00:00:00Z"}]))
        self.run_cli("sync", "--origin", "board", "--file", str(f))
        self.run_cli("snooze", "b1", "--until", "2026-01-20")
        f.write_text(json.dumps([{"id": "b1", "kind": "todo", "title": "T2"}]))
        self.now = T0 + timedelta(days=1)
        self.run_cli("sync", "--origin", "board", "--file", str(f))
        it = self.item("b1")
        self.assertEqual((it["title"], it["since"], it["snooze_until"]), ("T2", "2026-01-02T00:00:00Z", "2026-01-20"))

    def test_prune_after_two_days(self):
        self.run_cli("add", "--kind", "todo", "--title", "x", "--id", "t1")
        self.run_cli("done", "t1")
        self.now = T0 + timedelta(days=2, hours=1)
        self.run_cli("add", "--kind", "todo", "--title", "y", "--id", "t2")
        self.assertEqual([i["id"] for i in self.data()["items"]], ["t2"])

    def test_meeting_set_and_clear(self):
        self.assertEqual(self.run_cli("meeting", "--title", "Planning", "--at", "2026-01-14T15:00:00-06:00")[0], 0)
        self.assertEqual(self.data()["next_meeting"]["title"], "Planning")
        self.run_cli("meeting", "--clear")
        self.assertIsNone(self.data()["next_meeting"])
        self.assertEqual(self.run_cli("meeting", "--title", "x")[0], 1)

    def test_bad_kind_rejected(self):
        code, _, _ = self.run_cli("add", "--kind", "review", "--title", "x")
        self.assertEqual(code, 2)
        f = self.home / "items.json"
        f.write_text(json.dumps([{"id": "b1", "kind": "merge", "title": "x"}]))
        self.assertEqual(self.run_cli("sync", "--origin", "board", "--file", str(f))[0], 1)

    def test_list(self):
        self.run_cli("add", "--kind", "todo", "--title", "Book travel", "--id", "t1", "--due", "2026-01-20")
        _, out, _ = self.run_cli("list")
        self.assertEqual(out.strip(), "t1 | todo | Book travel | 2026-01-20")


if __name__ == "__main__":
    unittest.main()
