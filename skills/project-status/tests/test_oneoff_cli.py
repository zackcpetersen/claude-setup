"""Tests for add_oneoff.py. Run: python3 -m unittest discover -s skills/project-status/tests"""

import datetime
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "add_oneoff.py"


class OneOffCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "projects.json"
        self.file.write_text(json.dumps({"projects": [], "one_offs": [{"title": "Sign two bank forms", "state": "not started"}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *argv):
        return subprocess.run([sys.executable, str(TOOL), str(self.file), *argv], capture_output=True, text=True)

    def test_done_sets_state_and_done_on(self):
        r = self.run_tool("--done", "bank forms")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(self.file.read_text())["one_offs"][0]
        self.assertEqual((o["state"], o["done_on"]), ("done", datetime.date.today().isoformat()))

    def test_add_keeps_fields(self):
        r = self.run_tool("Book travel", "--needs-me", "--due", "2026-01-20")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(self.file.read_text())["one_offs"][1]
        self.assertEqual((o["title"], o["needs_me"], o["due"]), ("Book travel", True, "2026-01-20"))
        self.assertNotIn("done_on", o)


if __name__ == "__main__":
    unittest.main()
