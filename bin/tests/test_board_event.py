"""Tests for bin/board-event, in a temp BOARD_EVENTS_DIR only. Run: python3 -m unittest bin/tests/test_board_event.py"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("board_event", str(BIN / "board-event"))
_spec = importlib.util.spec_from_loader("board_event", _loader)
B = importlib.util.module_from_spec(_spec)
_loader.exec_module(B)

NOON = datetime(2026, 11, 20, 18, 30, 12, tzinfo=timezone.utc)  # 11:30 local in Denver


class BoardEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "events"
        env = mock.patch.dict(os.environ, {"BOARD_EVENTS_DIR": str(self.dir), "TZ": "America/Denver"})
        env.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(env.stop)
        self.now = NOON

    def run_cli(self, *args, now=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(B, "utcnow", return_value=now or self.now), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = B.main(list(args))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def add(self, *args, now=None):
        code, out, err = self.run_cli("add", *args, now=now)
        self.assertEqual(code, 0, err)
        return out.split()[1]

    def lines(self, day="2026-11-20"):
        return [json.loads(x) for x in (self.dir / f"{day}.jsonl").read_text().splitlines()]

    def test_add_writes_one_valid_line(self):
        code, out, _ = self.run_cli("add", "merged", "billing-migration", "PR merged",
                                    "--link", "https://example.invalid/pr/1", "--ref", "owner/repo#12")
        self.assertEqual((code, out), (0, "added 20261120T183012Z-0001\n"))
        [ev] = self.lines()
        self.assertEqual(ev["ts"], "2026-11-20T18:30:12Z")
        self.assertEqual((ev["v"], ev["day"], ev["kind"], ev["by"], ev["urgent"]), (1, "2026-11-20", "merged", "main", False))
        self.assertEqual(ev["links"], ["https://example.invalid/pr/1"])
        self.assertEqual(len(ev["dedupe"]), 12)
        self.assertEqual(self.add("note", "k", "two", "--by", "implementer"), "20261120T183012Z-0002")  # same second
        with mock.patch.dict(os.environ, {"BOARD_EVENT_BY": "pr-agent"}):
            self.add("note", "k", "three")
        self.assertEqual([e["by"] for e in self.lines()], ["main", "implementer", "pr-agent"])

    def test_validation_errors_exit_2_and_write_nothing(self):
        bad = [("add", "shipped", "k", "text"), ("add", "note", "k", "x" * 301),
               ("add", "note", "k", "two\nlines"), ("add", "note", "k", "t", "--field", "nokey"),
               ("add", "note", "k", "t", "--link", "ftp://x"),
               ("add", "note", "k", "t", "--field", "body=" + "b" * 6200),
               ("add", "note", "k", "t", "--field", "a=" + "b" * 6000, "--field", "c=" + "d" * 3000)]
        for args in bad:
            with self.subTest(args=args[1:3]):
                self.assertEqual(self.run_cli(*args)[0], 2)
        self.assertFalse((self.dir / "2026-11-20.jsonl").exists())

    def test_dedupe_same_and_previous_day_with_override(self):
        first = self.add("merged", "k", "PR merged", "--link", "https://example.invalid/1")
        code, out, _ = self.run_cli("add", "merged", "k", "PR merged", "--link", "https://example.invalid/1")
        self.assertEqual((code, out), (0, f"exists {first}\n"))
        self.assertEqual(len(self.lines()), 1)
        old = self.add("merged", "k", "PR merged", now=datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(self.run_cli("add", "merged", "k", "PR merged")[1], f"exists {old}\n")  # yesterday's file
        self.add("note", "k", "first wording", "--dedupe", "run-7")
        self.assertTrue(self.run_cli("add", "note", "k", "second wording", "--dedupe", "run-7")[1].startswith("exists"))
        self.add("job-progress", "k", "Backfill moved", "--field", "job=Backfill", "--field", "done=10")
        self.add("job-progress", "k", "Backfill moved", "--field", "job=Backfill", "--field", "done=20")
        self.assertEqual(len(self.lines()), 4)  # a new count is a new event

    def test_failed_and_needs_you_are_urgent_and_never_deduped(self):
        for kind in ("failed", "needs-you"):
            for _ in range(2):
                code, out, _ = self.run_cli("add", kind, "k", "CI failed")
                self.assertEqual(code, 0)
                self.assertRegex(out, rf"^added \S+\nURGENT \S+ {kind} k: CI failed\n$")
        self.assertEqual(len(self.lines()), 4)
        self.assertTrue(all(e["urgent"] for e in self.lines()))
        self.add("failed", "k", "run failed", "--dedupe", "failed:run-9")
        self.assertTrue(self.run_cli("add", "failed", "k", "run failed", "--dedupe", "failed:run-9")[1].startswith("exists"))

    def test_urgent_flags_and_field_types(self):
        self.assertNotIn("URGENT", self.run_cli("add", "failed", "k", "flaky", "--no-urgent")[1])
        self.assertIn("URGENT", self.run_cli("add", "note", "k", "look now", "--urgent")[1])
        self.add("job-progress", "k", "moved", "--field", "done=134000", "--field", "neg=-3",
                 "--field", "ok=true", "--field", "off=false", "--field", "eta=2026-12-01", "--field", "who=a=b")
        self.assertEqual(self.lines()[-1]["fields"],
                         {"done": 134000, "neg": -3, "ok": True, "off": False, "eta": "2026-12-01", "who": "a=b"})

    def test_reraised_wait_after_clear_is_written(self):
        link = "https://example.invalid/thread/1"
        wait = self.add("waiting-on", "k", "Waiting on the export file", "--link", link)
        self.assertTrue(self.run_cli("add", "waiting-on", "k", "Waiting on the export file", "--link", link)[1].startswith("exists"))
        self.add("cleared", "k", "Export file arrived", "--field", f"clears={wait}")
        self.add("waiting-on", "k", "Waiting on the export file", "--link", link)
        self.add("needs-you", "k", "Approve it", "--link", link, "--dedupe", "ask-1")
        self.add("cleared", "k", "Approved", "--link", link)
        self.add("needs-you", "k", "Approve it", "--link", link, "--dedupe", "ask-1")
        self.assertEqual([e["kind"] for e in self.lines()],
                         ["waiting-on", "cleared", "waiting-on", "needs-you", "cleared", "needs-you"])

    def test_unwritable_folder_exits_1_with_warning(self):
        blocker = Path(self.tmp.name) / "afile"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {"BOARD_EVENTS_DIR": str(blocker / "events")}):
            code, out, err = self.run_cli("add", "note", "k", "text")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("warning: event not logged:"))

    def test_torn_last_line_is_skipped_and_next_add_starts_a_new_line(self):
        first = self.add("note", "k", "one")
        with open(self.dir / "2026-11-20.jsonl", "a") as f:
            f.write('{"v": 1, "id": "torn')
        second = self.add("note", "k", "two")
        code, out, err = self.run_cli("today", "--json")
        self.assertEqual([json.loads(x)["id"] for x in out.splitlines()], [first, second])
        self.assertEqual(err.count("warning:"), 1)

    def test_parallel_adds_keep_every_line_and_unique_ids(self):
        script = ("import importlib.machinery as m, importlib.util as u, sys\n"
                  "L = m.SourceFileLoader('b', sys.argv[1]); B = u.module_from_spec(u.spec_from_loader('b', L))\n"
                  "L.exec_module(B)\n"
                  "for i in range(25):\n"
                  "    assert B.main(['add', 'note', 'k', f'w{sys.argv[2]} n{i}']) == 0\n")
        procs = [subprocess.Popen([sys.executable, "-c", script, str(BIN / "board-event"), str(w)],
                                  stdout=subprocess.DEVNULL) for w in range(8)]
        self.assertEqual([p.wait() for p in procs], [0] * 8)
        events = [json.loads(x) for f in sorted(self.dir.glob("*.jsonl")) for x in f.read_text().splitlines()]
        ids = [e["id"] for e in events]
        self.assertEqual(len(ids), 200)
        self.assertEqual(ids, sorted(set(ids)))

    def test_since_id_across_day_files_with_filters(self):
        for args in (("today",), ("since", "20261120T000000Z-0001")):  # no folder yet: nothing, exit 0
            self.assertEqual(self.run_cli(*args), (0, "", ""))
        old = self.add("merged", "a", "old", now=datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc))
        mid = self.add("failed", "b", "broke", "--link", "https://example.invalid/r/1",
                       now=datetime(2026, 11, 19, 19, 0, tzinfo=timezone.utc))
        new = self.add("merged", "a", "new")
        self.assertEqual(self.run_cli("since", old)[1],
                         f"{mid} failed b: broke [https://example.invalid/r/1]\n{new} merged a: new\n")
        self.assertEqual(self.run_cli("since", old, "--kind", "merged")[1], f"{new} merged a: new\n")
        self.assertEqual(self.run_cli("since", old, "--key", "b", "--json")[1].count("\n"), 1)
        self.assertEqual(self.run_cli("today")[1], f"{new} merged a: new\n")  # today's file only

    def test_since_iso_time_and_unknown_id(self):
        self.add("note", "k", "before", now=datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc))
        after = self.add("note", "k", "after")
        self.assertEqual(self.run_cli("since", "2026-11-20T16:00:00Z")[1], f"{after} note k: after\n")
        self.assertEqual(self.run_cli("since", "2026-11-20T09:00:00-07:00")[1], f"{after} note k: after\n")
        self.assertEqual(self.run_cli("since", "20261120T170000Z-0042")[1], f"{after} note k: after\n")
        self.assertEqual(self.run_cli("since", "yesterday")[0], 2)

    def test_since_across_utc_midnight_finds_previous_local_day_file(self):
        late = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)  # 20:00 on 11-20 in Denver
        ev = self.add("merged", "k", "late merge", now=late)
        self.assertTrue((self.dir / "2026-11-20.jsonl").exists())
        code, out, _ = self.run_cli("since", "20261121T020000Z-0001", now=late)
        self.assertEqual(out, f"{ev} merged k: late merge\n")


if __name__ == "__main__":
    unittest.main()
