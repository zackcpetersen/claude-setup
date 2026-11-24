"""Tests for apply_events.py and the shared projects.json lock. Run: python3 -m unittest discover -s skills/project-status/tests"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPLY = HERE.parent / "apply_events.py"
JOB = HERE.parent / "job.py"
ONEOFF = HERE.parent / "add_oneoff.py"
NOW = "2026-01-14T18:00:00Z"
DAY = "2026-01-14"


def ev(n, kind, key, text, day=DAY, **extra):
    hh = 10 + n // 60
    e = {"v": 1, "id": f"{day.replace('-', '')}T{hh:02d}{n % 60:02d}00Z-0001", "ts": f"{day}T{hh:02d}:{n % 60:02d}:00Z",
         "day": day, "key": key, "kind": kind, "text": text, "urgent": False, "by": "main"}
    e.update(extra)
    return e


class ApplyEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.events = self.dir / "events"
        self.events.mkdir()
        self.file = self.dir / "projects.json"
        (self.dir / "config.json").write_text(json.dumps({"tz": "UTC"}))
        self.write({"as_of": "2026-01-01T00:00:00Z", "zz_unknown": {"keep": True},
                    "projects": [
                        {"id": "billing-migration", "name": "Billing", "epic": "PROJ-1", "status": "On track",
                         "progress_pct": 40, "summary": "s", "needs_me": [{"ask": "Pick a cutover day", "ticket": "PROJ-9"}],
                         "breakdown": [{"group": "g", "items": [{"text": "t", "state": "done", "ref": "PROJ-12"}]}],
                         "jobs": [{"label": "Backfill", "done": 10, "total": 100}], "recent_progress": [], "decisions": []},
                        {"id": "search-revamp", "name": "Search"}],
                    "waiting_on": [],
                    "one_offs": [{"title": "Renew cert", "state": "not started", "ref": "OPS-3"}]})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.file.write_text(json.dumps(data, indent=2))

    def data(self):
        return json.loads(self.file.read_text())

    def log(self, *events):
        for e in events:
            with open(self.events / f"{e['day']}.jsonl", "a") as fh:
                fh.write(json.dumps(e) + "\n")

    def run_apply(self, *extra, now=NOW):
        return subprocess.run([sys.executable, str(APPLY), str(self.file), "--events-dir", str(self.events),
                               "--now", now, *extra], capture_output=True, text=True,
                              env={**os.environ, "TZ": "UTC"})  # "today" is the machine's local day

    def project(self, pid="billing-migration"):
        return next(p for p in self.data()["projects"] if p["id"] == pid)

    # ---------- kinds ----------

    def test_progress_kinds_and_decision(self):
        self.log(ev(1, "merged", "billing-migration", "PR merged"), ev(2, "deployed", "billing-migration", "Shipped"),
                 ev(3, "run-finished", "billing-migration", "Chunk 3 copied"), ev(4, "note", "billing-migration", "A note"),
                 ev(5, "decision", "billing-migration", "Cut over Friday"))
        r = self.run_apply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("applied 5, skipped 0, unplaced 0", r.stdout)
        p = self.project()
        self.assertEqual([x["text"] for x in p["recent_progress"]],
                         ["PR merged", "Shipped", "Chunk 3 copied", "A note", "Cut over Friday"])
        self.assertEqual(p["decisions"], [{"date": DAY, "decision": "Cut over Friday"}])
        self.assertEqual(self.data()["events_cursor"], ev(5, "x", "x", "x")["id"])
        self.assertEqual(self.data()["as_of"], NOW)

    def test_job_progress_and_done(self):
        self.log(ev(1, "job-progress", "billing-migration", "Backfill moved",
                    fields={"job": "backfill", "done": 50, "total": 100, "per_day": 10}),
                 ev(2, "job-progress", "billing-migration", "New job", fields={"job": "Export", "done": 1, "total": 4}))
        self.run_apply()
        jobs = {j["label"]: j for j in self.project()["jobs"]}
        self.assertEqual((jobs["Backfill"]["done"], jobs["Backfill"]["per_day"]), (50, 10))
        self.assertEqual(jobs["Backfill"]["updated"], f"{DAY}T10:01:00Z")
        self.assertEqual(jobs["Export"]["total"], 4)
        self.log(ev(3, "job-done", "billing-migration", "Backfill done", fields={"job": "Backfill"}))
        self.run_apply()
        p = self.project()
        self.assertEqual([j["label"] for j in p["jobs"]], ["Export"])
        self.assertIn({"date": DAY, "text": "Finished Backfill"}, p["recent_progress"])

    def test_job_done_replay_on_removed_job_is_skipped(self):
        self.log(ev(1, "job-done", "billing-migration", "Gone", fields={"job": "Nope"}))
        r = self.run_apply()
        self.assertEqual(r.returncode, 0)
        self.assertIn("applied 0, skipped 1, unplaced 0", r.stdout)

    def test_needs_you_and_waiting_on(self):
        link = "https://github.com/owner/repo/pull/12"
        self.log(ev(1, "needs-you", "PROJ-12", "Approve the plan", fields={"due": "2026-01-16", "effort": "5m"}),
                 ev(2, "waiting-on", "billing-migration", "Review on the PR", links=[link], fields={"who": "Ana"}),
                 ev(3, "needs-you", "billing-migration", "Pick a cutover day"))  # same ask already there
        r = self.run_apply()
        self.assertIn("applied 2, skipped 1", r.stdout)
        asks = self.project()["needs_me"]
        self.assertEqual(asks[-1], {"ask": "Approve the plan", "ticket": "PROJ-12", "due": "2026-01-16", "effort": "5m"})
        self.assertEqual(len(asks), 2)
        w = self.data()["waiting_on"][0]
        # 2026-01-14 is a Wednesday: three business days later is Monday the 19th
        self.assertEqual(w, {"person": "Ana", "what": "Review on the PR", "project_id": "billing-migration",
                             "since": DAY, "nudge_due": "2026-01-19", "link": link})

    def test_cleared_by_link_by_id_and_oneoff(self):
        link = "https://github.com/owner/repo/pull/12"
        ask = ev(1, "needs-you", "billing-migration", "Approve it", links=[link + "#discussion"])
        wait = ev(2, "waiting-on", "billing-migration", "Ana reviews", fields={"who": "Ana"})
        self.log(ask, wait)
        self.run_apply()
        self.log(ev(3, "cleared", "billing-migration", "Approved", links=[link]),
                 ev(4, "cleared", "billing-migration", "Ana replied", fields={"clears": wait["id"]}),
                 ev(5, "cleared", "OPS-3", "Cert renewed"),
                 ev(6, "cleared", "billing-migration", "Nothing matches", links=["https://example.com/x"]))
        r = self.run_apply()
        self.assertIn("applied 3, skipped 0, unplaced 1", r.stdout)
        self.assertIn("unplaced " + ev(6, "x", "x", "x")["id"] + " cleared billing-migration: Nothing matches", r.stdout)
        self.assertEqual([a["ask"] for a in self.project()["needs_me"]], ["Pick a cutover day"])
        self.assertEqual(self.data()["waiting_on"], [])
        o = self.data()["one_offs"][0]
        self.assertEqual((o["state"], o["done_on"]), ("done", DAY))

    def test_no_change_kinds_and_failed(self):
        self.log(ev(1, "run-started", "billing-migration", "Started"), ev(2, "goal-tick", "billing-migration", "Goal"),
                 ev(3, "draft-created", "billing-migration", "Draft", fields={"draft_id": "d1"}),
                 ev(4, "draft-sent", "billing-migration", "Sent", fields={"draft_id": "d1"}),
                 ev(5, "failed", "billing-migration", "Chunk 4 failed", urgent=True))
        before = self.project()
        r = self.run_apply()
        self.assertIn("applied 0, skipped 4, unplaced 1", r.stdout)
        self.assertIn("failed billing-migration: Chunk 4 failed", r.stdout)
        self.assertEqual(self.project(), before)

    # ---------- resolution ----------

    def test_project_resolution_order(self):
        self.log(ev(1, "note", "PROJ-1", "by epic"), ev(2, "note", "PROJ-12", "by breakdown ref"),
                 ev(3, "note", "PROJ-9", "by needs_me ticket"),
                 ev(4, "note", "PROJ-1", "project field wins", project="search-revamp"),
                 ev(5, "note", "search-revamp", "by id"), ev(6, "note", "other", "no project"),
                 ev(7, "note", "OPS-3", "one-offs take only cleared"))
        r = self.run_apply()
        self.assertIn("applied 5, skipped 0, unplaced 2", r.stdout)
        self.assertEqual([x["text"] for x in self.project()["recent_progress"]],
                         ["by epic", "by breakdown ref", "by needs_me ticket"])
        self.assertEqual([x["text"] for x in self.project("search-revamp")["recent_progress"]],
                         ["project field wins", "by id"])
        self.assertEqual(self.data()["events_cursor"], ev(7, "x", "x", "x")["id"])

    # ---------- idempotency, cursor, dates ----------

    def test_second_run_is_byte_identical(self):
        self.log(ev(1, "merged", "billing-migration", "PR merged"), ev(2, "needs-you", "billing-migration", "Ask"))
        self.run_apply()
        first = self.file.read_bytes()
        r = self.run_apply()
        self.assertIn("applied 0, skipped 0, unplaced 0", r.stdout)
        self.assertEqual(self.file.read_bytes(), first)

    def test_cursor_reset_does_not_duplicate(self):
        self.log(ev(1, "merged", "billing-migration", "PR merged"), ev(2, "decision", "billing-migration", "Go"),
                 ev(3, "needs-you", "billing-migration", "Ask", links=["https://example.com/a"]),
                 ev(4, "waiting-on", "billing-migration", "Wait", fields={"who": "Bo"}),
                 ev(5, "job-progress", "billing-migration", "Export moved", fields={"job": "Export", "done": 1}),
                 ev(6, "job-done", "billing-migration", "Export done", fields={"job": "Export"}))
        self.run_apply()
        first = self.data()
        self.assertEqual([r["text"] for r in first["projects"][0]["recent_progress"]].count("Finished Export"), 1)
        d = self.data()
        del d["events_cursor"]
        self.write(d)
        self.run_apply()
        # the replayed job-progress brings the job back for a moment, then job-done removes it again
        self.assertEqual(self.data(), first)

    def test_replayed_ask_with_later_clear_is_not_readded(self):
        link = "https://example.com/ask"
        self.log(ev(1, "needs-you", "billing-migration", "Ask", links=[link]),
                 ev(2, "cleared", "billing-migration", "Done", links=[link]),
                 ev(3, "waiting-on", "billing-migration", "Wait", fields={"who": "Bo"}))
        self.log(ev(4, "cleared", "billing-migration", "Bo replied", fields={"clears": ev(3, "x", "x", "x")["id"]}))
        r = self.run_apply()
        # the asks are skipped, and their clears have nothing left to remove: skipped too, never unplaced
        self.assertIn("applied 0, skipped 4, unplaced 0", r.stdout)
        self.assertEqual(len(self.project()["needs_me"]), 1)
        self.assertEqual(self.data()["waiting_on"], [])

    def test_clear_naming_a_wait_keeps_other_rows_on_the_same_link(self):
        pr = "https://github.com/owner/repo/pull/12"
        d = self.data()
        d["one_offs"].append({"title": "Watch PR 12", "state": "not started", "ref": pr})
        d["waiting_on"].append({"person": "Bo", "what": "Bo reviews too", "project_id": "search-revamp", "link": pr})
        self.write(d)
        wait = ev(1, "waiting-on", "billing-migration", "Ana reviews", links=[pr], fields={"who": "Ana"})
        self.log(wait, ev(2, "needs-you", "billing-migration", "Merge PR 12", links=[pr + "#discussion"]))
        self.run_apply()
        # Ana's wait shares Bo's link, so add_waiting skipped it: seed it by hand, as a gather would
        d = self.data()
        d["waiting_on"].append({"person": "Ana", "what": "Ana reviews", "project_id": "billing-migration", "link": pr})
        self.write(d)
        self.log(ev(4, "cleared", "billing-migration", "Ana approved", links=[pr], fields={"clears": wait["id"]}))
        r = self.run_apply()
        self.assertIn("applied 1, skipped 0, unplaced 0", r.stdout)
        self.assertIn("Merge PR 12", [a["ask"] for a in self.project()["needs_me"]])
        self.assertEqual([w["what"] for w in self.data()["waiting_on"]], ["Bo reviews too"])
        self.assertEqual(self.data()["one_offs"][-1]["state"], "not started")

    def test_job_fields_from_events_are_normalized_and_bad_ones_unplaced(self):
        self.log(ev(1, "job-progress", "billing-migration", "Backfill moved",
                    fields={"job": "Backfill", "done": "12.5", "total": "60", "per_day": "2.5", "eta": "2026-01-20"}),
                 ev(2, "job-progress", "billing-migration", "Bad eta", fields={"job": "Backfill", "done": 20, "eta": "soon"}))
        r = self.run_apply()
        self.assertIn("applied 1, skipped 0, unplaced 1", r.stdout)
        j = self.project()["jobs"][0]
        self.assertEqual((j["done"], j["total"], j["per_day"], j["eta"]), (12.5, 60, 2.5, "2026-01-20"))

    def test_non_id_cursor_warns_and_is_left_alone(self):
        d = self.data()
        d["events_cursor"] = "2026-01-12T18:00:00Z"
        self.write(d)
        self.log(ev(1, "note", "billing-migration", "today"))
        r = self.run_apply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("is not an event id", r.stderr)
        self.assertEqual(self.data()["events_cursor"], "2026-01-12T18:00:00Z")
        self.assertEqual([x["text"] for x in self.project()["recent_progress"]], ["today"])

    def test_missing_cursor_starts_at_today_and_dates_come_from_event_day(self):
        self.log(ev(1, "note", "billing-migration", "yesterday", day="2026-01-13"),
                 ev(1, "note", "billing-migration", "today"))
        self.run_apply()
        self.assertEqual(self.project()["recent_progress"], [{"date": DAY, "text": "today"}])
        # a late run days after still dates the edit with the event's day
        self.log(ev(9, "note", "billing-migration", "late"))
        self.run_apply(now="2026-01-20T18:00:00Z")
        self.assertEqual(self.project()["recent_progress"][-1], {"date": DAY, "text": "late"})

    def test_missing_cursor_today_is_machine_local_day_not_config_tz(self):
        # config tz is UTC+14 (2026-01-15 at NOW), the machine is UTC (2026-01-14): board-event's file is the 14th
        (self.dir / "config.json").write_text(json.dumps({"tz": "Pacific/Kiritimati"}))
        self.log(ev(1, "note", "billing-migration", "machine day"))
        r = subprocess.run([sys.executable, str(APPLY), str(self.file), "--events-dir", str(self.events), "--now", NOW],
                           capture_output=True, text=True, env={**os.environ, "TZ": "UTC"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.project()["recent_progress"], [{"date": DAY, "text": "machine day"}])

    def test_cursor_walks_across_day_files(self):
        d = self.data()
        d["events_cursor"] = ev(1, "x", "x", "x", day="2026-01-12")["id"]
        self.write(d)
        self.log(ev(1, "note", "billing-migration", "at cursor", day="2026-01-12"),
                 ev(2, "note", "billing-migration", "after", day="2026-01-12"),
                 ev(1, "note", "billing-migration", "next day", day="2026-01-13"))
        self.run_apply()
        self.assertEqual([x["text"] for x in self.project()["recent_progress"]], ["after", "next day"])

    def test_missing_folder_only_sets_as_of(self):
        self.tmp2 = self.dir / "nope"
        before = self.data()
        r = subprocess.run([sys.executable, str(APPLY), str(self.file), "--events-dir", str(self.tmp2), "--now", NOW],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        before["as_of"] = NOW
        self.assertEqual(self.data(), before)
        self.assertNotIn("events_cursor", self.data())

    def test_torn_line_is_skipped_with_warning(self):
        self.log(ev(1, "note", "billing-migration", "good"))
        with open(self.events / f"{DAY}.jsonl", "a") as fh:
            fh.write('{"id": "torn')
        r = self.run_apply()
        self.assertIn("warning: skipped unreadable line", r.stderr)
        self.assertEqual(self.data()["events_cursor"], ev(1, "x", "x", "x")["id"])

    def test_keeps_unknown_keys_and_oneoffs(self):
        self.log(ev(1, "note", "billing-migration", "n"))
        self.run_apply()
        d = self.data()
        self.assertEqual(d["zz_unknown"], {"keep": True})
        self.assertEqual(d["one_offs"][0]["title"], "Renew cert")
        self.assertEqual(self.project()["progress_pct"], 40)

    def test_dry_run_writes_nothing(self):
        self.log(ev(1, "note", "billing-migration", "n"))
        before = self.file.read_bytes()
        r = self.run_apply("--dry-run")
        self.assertIn("applied 1", r.stdout)
        self.assertIn("dry run", r.stdout)
        self.assertEqual(self.file.read_bytes(), before)

    # ---------- shared lock ----------

    def test_parallel_job_and_apply_lose_nothing(self):
        for i in range(20):
            self.log(ev(i, "note", "billing-migration", f"note {i}"))

        def apply_run(i):
            return self.run_apply(now=f"2026-01-14T18:00:{i:02d}Z")

        def job_run(i):
            return subprocess.run([sys.executable, str(JOB), str(self.file), "set", "billing-migration", f"Job {i}",
                                   "--done", str(i), "--now", NOW], capture_output=True, text=True)

        with ThreadPoolExecutor(max_workers=8) as pool:
            runs = [pool.submit(apply_run, i) for i in range(20)] + [pool.submit(job_run, i) for i in range(20)]
            for r in runs:
                self.assertEqual(r.result().returncode, 0, r.result().stderr)
        p = self.project()
        self.assertEqual(len(p["recent_progress"]), 20)
        self.assertEqual({j["label"] for j in p["jobs"]}, {"Backfill"} | {f"Job {i}" for i in range(20)})

    def test_oneoff_cli_uses_the_lock_and_keeps_cursor(self):
        d = self.data()
        d["events_cursor"] = "20260114T100000Z-0001"
        self.write(d)
        r = subprocess.run([sys.executable, str(ONEOFF), str(self.file), "New thing"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.data()["events_cursor"], "20260114T100000Z-0001")
        self.assertEqual(self.data()["one_offs"][-1]["title"], "New thing")


if __name__ == "__main__":
    unittest.main()
