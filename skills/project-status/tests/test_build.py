"""End-to-end tests for build.py on fixtures. Run: python3 -m unittest discover -s skills/project-status/tests"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent.parent
BUILD = SKILL / "build.py"
FIX = HERE / "fixtures" / "home"
NOW = "2026-01-14T18:00:00Z"


def page_data(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        shutil.copytree(FIX, self.home)
        self.out = self.dir / "out.html"

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, data, *extra):
        r = subprocess.run([sys.executable, str(BUILD), str(data), str(self.out), *extra], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, self.out.read_text()

    def test_fixture_home_builds(self):
        r, html = self.build(self.home / "projects.json", "--config", str(self.home / "config.json"), "--home", str(self.home),
                             "--now", NOW, "--no-state")
        for marker in ("__TITLE__", "/*__CSS__*/", "/*__THEME__*/", "/*__JS__*/", "__DATA__"):
            self.assertNotIn(marker, html)
        self.assertIn("<title>Sam's Status and Plans</title>", html)
        self.assertIn("--canvas:#E9EEF2", html)
        self.assertNotIn("</script> today", html)
        d = page_data(html)
        bands = [i["band"] for i in d["inbox"]["items"]]
        self.assertEqual(bands, sorted(bands))
        self.assertEqual(d["today"], "2026-01-14")
        self.assertEqual(d["config"]["inbox"], {"cap": 3, "home_count": 2})
        self.assertNotIn("unsure", d)
        self.assertIn("Sign off the rollback plan </script> today.", [i["title"] for i in d["inbox"]["items"]])
        merged = [i for i in d["inbox"]["items"] if i["id"] == "gh:acme/billing#91"]
        self.assertEqual(len(merged), 1)
        self.assertEqual((merged[0]["title"], merged[0]["kind"]), ("Merge the region 3 cutover.", "merge"))
        self.assertEqual([s["state"] for s in d["sources"]], ["ok", "ok", "ok", "ok", "ok"])
        self.assertEqual(d["sources"][-1]["name"], "stats")
        self.assertEqual(d["strip"]["next_meeting"]["time"], "15:00")
        self.assertIn("inbox items", r.stdout)

    def test_sample_without_home_writes_no_state(self):
        before = set(p for p in SKILL.rglob("*"))
        _, html = self.build(SKILL / "sample-data.json")
        d = page_data(html)
        self.assertEqual(d["sources"][1]["state"], "missing")
        self.assertEqual(set(p for p in SKILL.rglob("*")), before)
        self.assertFalse(any(SKILL.rglob("build.json")))

    def test_sample_home_builds(self):
        self.build(SKILL / "sample-data.json", "--home", str(SKILL / "sample-home"), "--no-state", "--now", "2026-01-12T18:00:00Z")
        self.assertFalse((SKILL / "sample-home" / "state").exists())

    def test_old_style_projects_file_builds(self):
        old = self.dir / "old.json"
        old.write_text(json.dumps({"as_of": "2026-01-12T17:00Z", "projects": [
            {"id": "a", "name": "A", "progress_pct": 10, "needs_me": [{"ask": "Do it", "ticket": "ENG-1", "due": "2026-01-15"}]}],
            "waiting_on": [{"person": "Ana", "what": "x", "project_id": "a", "since": "2026-01-02", "nudge_due": "2026-01-12"}]}))
        _, html = self.build(old, "--now", NOW)
        self.assertEqual(len(page_data(html)["inbox"]["items"]), 2)

    def test_broken_inbox_and_feed_mark_failing(self):
        (self.home / "inbox.json").write_text("{not json")
        (self.home / "feeds" / "github.json").write_text("")
        r, html = self.build(self.home / "projects.json", "--home", str(self.home), "--now", NOW, "--no-state")
        states = {s["name"]: s["state"] for s in page_data(html)["sources"]}
        self.assertEqual((states["session"], states["github"], states["slack"]), ("failing", "failing", "ok"))
        self.assertIn("warning", r.stderr)

    def test_no_state_flag(self):
        state = self.home / "state" / "build.json"
        self.build(self.home / "projects.json", "--home", str(self.home), "--now", NOW, "--no-state")
        self.assertFalse(state.exists())
        self.build(self.home / "projects.json", "--home", str(self.home), "--now", NOW)
        saved = json.loads(state.read_text())
        self.assertEqual(saved["date"], "2026-01-14")
        self.assertIn("gh:acme/billing#91", saved["open"])
        before = state.read_text()
        self.build(self.home / "projects.json", "--home", str(self.home), "--now", "2026-01-14T19:00:00Z", "--no-state")
        self.assertEqual(state.read_text(), before)

    def test_no_em_or_en_dashes(self):
        files = [p for p in SKILL.rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".css", ".html", ".json", ".md")]
        files += [REPO / "bin" / "status-feeds", REPO / "bin" / "eng-stats"]
        bad = [str(p) for p in files if p.exists() and any(chr(c) in p.read_text() for c in (0x2014, 0x2013))]
        self.assertEqual(bad, [])

    def fixture_build(self, *extra):
        return self.build(self.home / "projects.json", "--config", str(self.home / "config.json"), "--home", str(self.home),
                          "--now", NOW, "--no-state", *extra)

    def test_dashboard_data_in_fixture_build(self):
        r, html = self.fixture_build()
        d = page_data(html)
        for k in ("timeline", "pipeline", "waiting", "delivered", "jobs", "stats", "unlinked"):
            self.assertIn(k, d)
        self.assertEqual(d["jobs"]["billing-migration"][0]["eta"], "2026-01-22")
        self.assertIn("job", [e["kind"] for e in d["timeline"]["events"]])
        self.assertTrue(any(e["late"] and e["project_id"] == "search-revamp" for e in d["timeline"]["events"]))
        self.assertEqual([s["n"] for s in d["pipeline"]["stages"]], [1, 1, 1, 1])
        self.assertEqual(len(d["waiting"]["rows"]), 2)
        self.assertEqual([x["title"] for x in d["delivered"]], ["Confirm Ana got the export"])
        self.assertEqual(d["stats"]["login"], "sam")
        self.assertIn("stats ok", r.stdout)

    def test_no_stats_file(self):
        (self.home / "feeds" / "stats.json").unlink()
        _, html = self.fixture_build()
        d = page_data(html)
        self.assertIsNone(d["stats"])
        self.assertNotIn("stats", [s["name"] for s in d["sources"]])

    def test_broken_stats_file_marks_failing(self):
        (self.home / "feeds" / "stats.json").write_text("{nope")
        _, html = self.fixture_build()
        states = {s["name"]: s["state"] for s in page_data(html)["sources"]}
        self.assertEqual(states["stats"], "failing")

    def test_sample_without_home_has_timeline_only(self):
        _, html = self.build(SKILL / "sample-data.json", "--now", "2026-01-12T18:00:00Z")
        d = page_data(html)
        self.assertIsNone(d["pipeline"])
        self.assertIsNone(d["stats"])
        self.assertTrue(d["timeline"]["events"])

    def test_ticket_keys_link_with_tracker_url(self):
        _, html = self.fixture_build()
        d = page_data(html)
        ask = d["projects"][0]["needs_me"][0]
        self.assertEqual(ask["ticket_parts"], [{"text": "ENG-142", "url": "https://tracker.example.com/browse/ENG-142"}])
        self.assertNotIn("ENG-142", [u["text"] for u in d["unlinked"]])

    def test_unlinked_mention_warns_without_tracker_url(self):
        cfg = json.loads((self.home / "config.json").read_text())
        del cfg["tracker_url"]
        (self.home / "config.json").write_text(json.dumps(cfg))
        r, html = self.fixture_build()
        self.assertIn("ENG-142", [u["text"] for u in page_data(html)["unlinked"]])
        self.assertIn("warning: unlinked mention ENG-142", r.stderr)

    def test_page_has_rail_and_sheet_not_drawer(self):
        _, html = self.fixture_build()
        self.assertIn('id="rail"', html)
        self.assertIn('id="sheet"', html)
        self.assertNotIn('id="drawer"', html)
        self.assertIn('<meta charset="utf-8">', html)

    def test_no_hardcoded_workspace_hosts(self):
        files = [p for p in SKILL.rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".css", ".html", ".json", ".md")
                 and "fixtures" not in p.parts and p.name != "test_build.py"]
        files.append(REPO / "bin" / "eng-stats")
        bad = []
        for p in files:
            text = p.read_text() if p.exists() else ""
            for host in ("atlassian.net", "slack.com/archives", "notion.so", "notion.com"):
                for line in text.splitlines():
                    if host in line and "example" not in line and "FILL-IN" not in line and "acme" not in line:
                        bad.append(f"{p.name}: {host}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
