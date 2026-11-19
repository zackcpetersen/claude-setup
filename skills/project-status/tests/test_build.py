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
        self.assertIn("--canvas:#203040", html)
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
        self.assertEqual([s["state"] for s in d["sources"]], ["ok", "ok", "ok", "ok"])
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
        files.append(REPO / "bin" / "status-feeds")
        bad = [str(p) for p in files if p.exists() and any(chr(c) in p.read_text() for c in (0x2014, 0x2013))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
