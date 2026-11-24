"""Tests for job.py. Run: python3 -m unittest discover -s skills/project-status/tests"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOB = HERE.parent / "job.py"
NOW = "2026-01-14T18:00:00Z"


class JobCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "projects.json"
        self.file.write_text(json.dumps({"as_of": "2026-01-01T00:00:00Z", "projects": [
            {"id": "billing-migration", "name": "Billing migration", "status": "On track", "recent_progress": []}],
            "waiting_on": [], "zz_last": True}, indent=2))

    def tearDown(self):
        self.tmp.cleanup()

    def run_job(self, *argv):
        return subprocess.run([sys.executable, str(JOB), str(self.file), *argv], capture_output=True, text=True)

    def data(self):
        return json.loads(self.file.read_text())

    def test_set_creates_jobs_list(self):
        r = self.run_job("set", "billing-migration", "Backfill", "--done", "610000", "--total", "1000000",
                         "--unit", "files", "--per-day", "45000", "--now", NOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.data()
        job = d["projects"][0]["jobs"][0]
        self.assertEqual(job, {"label": "Backfill", "done": 610000, "total": 1000000, "unit": "files",
                               "per_day": 45000, "updated": NOW})
        self.assertEqual(d["as_of"], NOW)

    def test_second_set_updates_by_label_and_keeps_other_fields(self):
        self.run_job("set", "billing-migration", "Backfill", "--done", "10", "--total", "100", "--unit", "files", "--now", NOW)
        r = self.run_job("set", "billing-migration", "BACKFILL", "--done", "20", "--eta", "2026-02-01",
                         "--now", "2026-01-15T09:00:00Z")
        self.assertEqual(r.returncode, 0, r.stderr)
        jobs = self.data()["projects"][0]["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0], {"label": "Backfill", "done": 20, "total": 100, "unit": "files", "eta": "2026-02-01",
                                   "updated": "2026-01-15T09:00:00Z"})

    def test_unknown_project_exits_1(self):
        r = self.run_job("set", "nope", "Backfill", "--done", "1", "--now", NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("nope", r.stderr)

    def test_done_removes_and_logs_progress(self):
        self.run_job("set", "billing-migration", "Backfill", "--done", "100", "--total", "100", "--now", NOW)
        r = self.run_job("done", "billing-migration", "backfill", "--now", NOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.data()["projects"][0]
        self.assertEqual(p["jobs"], [])
        self.assertEqual(p["recent_progress"][-1]["text"], "Finished Backfill")
        self.assertRegex(p["recent_progress"][-1]["date"], r"^2026-01-1[45]$")

    def test_done_dates_in_config_tz(self):
        (self.dir / "config.json").write_text(json.dumps({"tz": "Pacific/Kiritimati"}))  # UTC+14
        self.run_job("set", "billing-migration", "Backfill", "--done", "1", "--now", NOW)
        self.run_job("done", "billing-migration", "Backfill", "--now", NOW)
        self.assertEqual(self.data()["projects"][0]["recent_progress"][-1]["date"], "2026-01-15")
        other = self.dir / "other.json"
        other.write_text(json.dumps({"tz": "Pacific/Pago_Pago"}))  # UTC-11
        self.run_job("set", "billing-migration", "Backfill", "--done", "1", "--now", NOW)
        self.run_job("done", "billing-migration", "Backfill", "--now", "2026-01-15T05:00:00Z", "--config", str(other))
        self.assertEqual(self.data()["projects"][0]["recent_progress"][-1]["date"], "2026-01-14")

    def test_done_without_match_exits_1(self):
        r = self.run_job("done", "billing-migration", "Backfill", "--now", NOW)
        self.assertEqual(r.returncode, 1)

    def test_other_keys_and_order_survive_and_no_tmp_left(self):
        self.run_job("set", "billing-migration", "Backfill", "--done", "1", "--now", NOW)
        d = self.data()
        self.assertEqual(list(d.keys()), ["as_of", "projects", "waiting_on", "zz_last"])
        self.assertEqual(list(d["projects"][0].keys())[:4], ["id", "name", "status", "recent_progress"])
        # the lock file stays on purpose (shared with add_oneoff.py and apply_events.py); no .tmp is left
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["projects.json", "projects.json.lock"])


if __name__ == "__main__":
    unittest.main()
