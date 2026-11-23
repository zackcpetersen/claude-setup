"""End-to-end tests for build.py on fixtures. Run: python3 -m unittest discover -s skills/project-status/tests"""

import base64
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

    def test_page_is_one_focus_screen(self):
        _, html = self.fixture_build()
        self.assertNotIn('id="rail"', html)
        self.assertIn('id="page"', html)
        self.assertIn('<meta charset="utf-8">', html)
        f = page_data(html)["focus"]
        for k in ("hero", "up_next", "running", "wins", "parked", "tiles", "feed_note", "cap", "up_next_shown"):
            self.assertIn(k, f)
        self.assertIsNotNone(f["hero"])
        self.assertTrue(f["hero"]["action"])

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


class Brand(unittest.TestCase):
    """The optional brand logo from config: inlined, cleaned, capped, and absent by default."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "out.html"

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, brand=None):
        cfg = {"title": "Example Status"}
        if brand is not None:
            cfg["brand"] = brand
        (self.dir / "config.json").write_text(json.dumps(cfg))
        r = subprocess.run([sys.executable, str(BUILD), str(SKILL / "sample-data.json"), str(self.out),
                            "--config", str(self.dir / "config.json"), "--now", NOW], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, page_data(self.out.read_text())["config"]

    def decode(self, uri):
        return base64.b64decode(uri.split(",", 1)[1]).decode()

    def test_no_brand_means_no_brand_payload(self):
        _, cfg = self.build()
        self.assertNotIn("brand", cfg)
        _, cfg = self.build({"name": "Example Co"})
        self.assertNotIn("brand", cfg)

    def test_svg_logo_is_inlined_and_cleaned(self):
        (self.dir / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)" viewBox="0 0 10 10">'
                                           '<script>alert(2)</script><a href="javascript:alert(3)"><rect onclick=\'x()\' width="10" height="10"/></a>'
                                           '<foreignObject><div>hi</div></foreignObject></svg>')
        _, cfg = self.build({"logo": "mark.svg", "name": "Example Co"})
        b = cfg["brand"]
        self.assertTrue(b["logo"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual(b["name"], "Example Co")
        svg = self.decode(b["logo"])
        for bad in ("onload", "onclick", "<script", "javascript:", "foreignObject"):
            self.assertNotIn(bad, svg)
        self.assertIn('<rect width="10" height="10"/>', svg)

    def test_dark_variant_and_png(self):
        (self.dir / "light.png").write_bytes(b"\x89PNG\r\n\x1a\nlight")
        (self.dir / "dark.png").write_bytes(b"\x89PNG\r\n\x1a\ndark")
        _, cfg = self.build({"logo": "light.png", "logo_dark": "dark.png"})
        self.assertTrue(cfg["brand"]["logo"].startswith("data:image/png;base64,"))
        self.assertNotEqual(cfg["brand"]["logo"], cfg["brand"]["logo_dark"])
        self.assertNotIn("name", cfg["brand"])

    def test_missing_variant_is_not_filled_from_the_other(self):
        (self.dir / "light.png").write_bytes(b"\x89PNG\r\n\x1a\nlight")
        _, cfg = self.build({"logo": "light.png"})
        self.assertIn("logo", cfg["brand"])
        self.assertNotIn("logo_dark", cfg["brand"])
        (self.dir / "dark.png").write_bytes(b"\x89PNG\r\n\x1a\ndark")
        _, cfg = self.build({"logo_dark": "dark.png"})
        self.assertIn("logo_dark", cfg["brand"])
        self.assertNotIn("logo", cfg["brand"])

    def test_non_utf8_svg_is_skipped(self):
        (self.dir / "latin.svg").write_bytes('<svg><title>caf\u00e9</title></svg>'.encode("latin-1"))
        r, cfg = self.build({"logo": "latin.svg"})
        self.assertNotIn("brand", cfg)
        self.assertIn("warning: brand logo latin.svg is not UTF-8 text", r.stderr)

    def test_relative_logo_resolves_next_to_a_symlinked_config(self):
        real = self.dir / "real"
        real.mkdir()
        (self.dir / "light.png").write_bytes(b"\x89PNG\r\n\x1a\nlight")
        (real / "config.json").write_text(json.dumps({"brand": {"logo": "light.png"}}))
        link = self.dir / "config-link.json"
        link.symlink_to(real / "config.json")
        r = subprocess.run([sys.executable, str(BUILD), str(SKILL / "sample-data.json"), str(self.out),
                            "--config", str(link), "--now", NOW], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("logo", page_data(self.out.read_text())["config"]["brand"])

    def test_bad_logos_warn_and_fall_back(self):
        (self.dir / "big.svg").write_text("<svg>" + "x" * 70000 + "</svg>")
        (self.dir / "notes.txt").write_text("hi")
        r, cfg = self.build({"logo": "big.svg", "logo_dark": "notes.txt"})
        self.assertNotIn("brand", cfg)
        self.assertIn("warning: brand logo big.svg is over 60 KB", r.stderr)
        self.assertIn("warning: brand logo notes.txt", r.stderr)
        r, cfg = self.build({"logo": "missing.svg"})
        self.assertNotIn("brand", cfg)
        self.assertIn("could not be read", r.stderr)


if __name__ == "__main__":
    unittest.main()
