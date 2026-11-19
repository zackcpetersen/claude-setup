"""Tests for bin/pr-precheck. Run: python3 -m unittest bin/tests/test_pr_precheck.py

Every test works in a temp folder with a temp git repo and a bare origin. Lint and
test commands are a small fake shell script set through a temp config, so no real
linter or test runner is needed.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent
SCRIPT = BIN / "pr-precheck"
_loader = importlib.machinery.SourceFileLoader("pr_precheck", str(SCRIPT))
_spec = importlib.util.spec_from_loader("pr_precheck", _loader)
P = importlib.util.module_from_spec(_spec)
_loader.exec_module(P)

FAKE = """#!/bin/sh
name=$1; shift
echo "$name $* VENV=${{VIRTUAL_ENV:-none}}" >> "{log}"
rc=0
[ -f "{dir}/$name.rc" ] && rc=$(cat "{dir}/$name.rc")
[ "$rc" -ne 0 ] && echo "offense from $name"
exit $rc
"""


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        gitcfg = self.home / "gitconfig"
        gitcfg.write_text("[user]\n\tname = T\n\temail = t@example.invalid\n[init]\n\tdefaultBranch = main\n")
        self.cfg_path = self.home / "pr-precheck.json"
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": str(gitcfg), "GIT_CONFIG_NOSYSTEM": "1",
                    "HOME": str(self.home), "PR_PRECHECK_CONFIG": str(self.cfg_path),
                    "VIRTUAL_ENV": str(self.home / "some-venv")}
        patch = mock.patch.dict(os.environ, self.env)
        patch.start()
        self.addCleanup(patch.stop)

        self.log = self.home / "calls.log"
        self.fake = self.home / "fake"
        self.fake.write_text(FAKE.format(log=self.log, dir=self.home))
        self.fake.chmod(0o755)

        origin = self.home / "origin.git"
        sh(self.home, "git", "init", "-q", "--bare", "-b", "main", str(origin))
        self.repo = self.home / "Projects" / "app"
        sh(self.home, "git", "clone", "-q", str(origin), str(self.repo))
        self.write("Gemfile", "source 'x'\n")
        self.write("app/models/user.rb", "class User\nend\n")
        self.write("old.rb", "x = 1\n")
        sh(self.repo, "git", "add", ".")
        sh(self.repo, "git", "commit", "-qm", "init")
        sh(self.repo, "git", "push", "-q", "origin", "main")
        sh(self.repo, "git", "remote", "set-head", "origin", "main")
        sh(self.repo, "git", "checkout", "-q", "-b", "feature")
        self.config()

    def write(self, rel, text, root=None):
        p = (root or self.repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def config(self, **extra):
        cfg = {"rb": {"fix": f"{self.fake} rbfix {{files}}", "check": f"{self.fake} rbcheck {{files}}",
                      "tests": f"{self.fake} rbtest {{files}}"},
               "py": {"fix": f"{self.fake} pyfix {{files}}", "check": f"{self.fake} pycheck {{files}}",
                      "tests": f"{self.fake} pytest {{files}}"}}
        cfg.update(extra)
        self.cfg_path.write_text(json.dumps(cfg))

    def rc(self, name, code):
        (self.home / f"{name}.rc").write_text(str(code))

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def run_script(self, *args, stdin=None, repo=None):
        cmd = [sys.executable, str(SCRIPT), *args]
        if args and args[0] in ("fix", "report"):
            cmd += ["--repo", str(repo or self.repo)]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=self.env)


class ChangedFiles(Base):
    def test_modified_added_untracked_not_deleted(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.write("added.rb", "y\n")
        sh(self.repo, "git", "add", "added.rb")
        self.write("loose.rb", "z\n")
        (self.repo / "old.rb").unlink()
        mb = P.merge_base(self.repo, None)
        self.assertEqual(P.changed_files(self.repo, mb), ["added.rb", "app/models/user.rb", "loose.rb"])


class Fix(Base):
    def test_fix_then_check_and_exit_codes(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        r = self.run_script("fix", "--no-tests")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        names = [c.split()[0] for c in self.calls()]
        self.assertEqual(names, ["rbfix", "rbcheck"])
        self.assertIn("rbcheck app/models/user.rb", self.calls()[1])
        self.rc("rbcheck", 1)
        r = self.run_script("fix", "--no-tests")
        self.assertEqual(r.returncode, 1)
        self.assertIn("offense from rbcheck", r.stdout)

    def test_missing_tool_is_skipped(self):
        self.config(rb={"fix": [], "check": "no-such-tool-xyz {files}", "tests": "none"})
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        r = self.run_script("fix")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("skipped: tool not found", r.stdout)

    def test_runner_reported_missing_tool_is_skipped(self):
        for i, (msg, code) in enumerate((("Command not found: ruff", 1),
                                          ("error: Failed to spawn: `ruff`\n  Caused by: No such file", 2),
                                          ("npm error code E404", 1))):
            runner = self.home / f"runner{i}"
            runner.write_text(f"#!/bin/sh\nprintf '%s\\n' \"{msg}\"\nexit {code}\n")
            runner.chmod(0o755)
            self.assertEqual(P.run_cmd(f"{runner} ruff x.py", self.home)[0], "skipped: tool not found (" + str(runner) + ")")
        self.assertEqual(P.run_cmd(f"{self.fake} other", self.home)[0], "ok")

    def test_all_skipped_writes_no_clean_stamp(self):
        self.config(rb={"fix": [], "check": "no-such-tool-xyz {files}", "tests": "none"})
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        r = self.run_script("fix")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("nothing checked", r.stdout)
        self.assertIn("precheck: skipped on this tree", self.run_script("report").stdout)
        self.assertNotIn("already clean", self.run_script("fix").stdout)

    def test_stamp(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.write("spec/models/user_spec.rb", "describe User\n")
        self.assertEqual(self.run_script("fix").returncode, 0)
        n = len(self.calls())
        self.assertGreater(n, 0)
        r = self.run_script("fix")
        self.assertIn("already clean for this tree", r.stdout)
        self.assertEqual(len(self.calls()), n)
        self.write("app/models/user.rb", "class User\n  y\nend\n")
        self.run_script("fix")
        m = len(self.calls())
        self.assertGreater(m, n)
        self.run_script("fix", "--force")
        self.assertGreater(len(self.calls()), m)

    def test_no_tests_run_writes_no_stamp(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.write("spec/models/user_spec.rb", "describe User\n")
        self.run_script("fix", "--no-tests")
        self.assertFalse(any(c.startswith("rbtest") for c in self.calls()))
        self.run_script("fix")
        self.assertTrue(any(c.startswith("rbtest spec/models/user_spec.rb") for c in self.calls()))

    def test_virtual_env_removed(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.run_script("fix", "--no-tests")
        self.assertTrue(self.calls())
        self.assertTrue(all(c.endswith("VENV=none") for c in self.calls()))


class Discovery(Base):
    def test_rb_py_ts_and_changed_tests(self):
        self.write("spec/models/user_spec.rb", "")
        self.write("spec/lib/tools/x_spec.rb", "")
        self.assertEqual(P.discover_tests("rb", self.repo, ["app/models/user.rb", "lib/tools/x.rb"]),
                         ["spec/lib/tools/x_spec.rb", "spec/models/user_spec.rb"])
        self.assertEqual(P.discover_tests("rb", self.repo, ["spec/other_spec.rb"]), ["spec/other_spec.rb"])
        py = self.home / "py"
        self.write("pkg/thing.py", "", root=py)
        self.write("tests/test_thing.py", "", root=py)
        sh(py.parent, "git", "init", "-q", str(py))
        self.assertEqual(P.discover_tests("py", py, ["pkg/thing.py"]), ["tests/test_thing.py"])
        ts = self.home / "ts"
        self.write("src/a.ts", "", root=ts)
        self.write("src/a.test.ts", "", root=ts)
        self.assertEqual(P.discover_tests("ts", ts, ["src/a.ts"]), ["src/a.test.ts"])

    def test_repo_tests_override_replaces_discovery(self):
        self.config(repos={"app": {"tests": f"{self.fake} repotests {{files}}"}})
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.write("spec/models/user_spec.rb", "")
        self.run_script("fix")
        names = [c.split()[0] for c in self.calls()]
        self.assertIn("repotests", names)
        self.assertNotIn("rbtest", names)

    def test_worktree_uses_main_checkout_key_and_tests_none(self):
        self.config(repos={"app": {"tests": "none", "rb": {"check": f"{self.fake} wtcheck {{files}}"}}})
        wt = self.home / "Projects" / "app-wt" / "feature2"
        sh(self.repo, "git", "worktree", "add", "-q", "-b", "feature2", str(wt))
        self.write("app/models/user.rb", "class User\n  x\nend\n", root=wt)
        self.write("spec/models/user_spec.rb", "", root=wt)
        r = self.run_script("fix", repo=wt)
        self.assertEqual(r.returncode, 0, r.stdout)
        names = [c.split()[0] for c in self.calls()]
        self.assertIn("wtcheck", names)
        self.assertNotIn("rbtest", names)


class Report(Base):
    def report(self, *args):
        r = self.run_script("report", "--json", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_size_generated_and_over(self):
        self.write("a.rb", "1\n2\n3\n")
        self.write("db/schema.rb", "x\n" * 100)
        self.write(".gitattributes", "gen/* linguist-generated\n")
        self.write("gen/data.txt", "y\n" * 50)
        sh(self.repo, "git", "add", ".")
        d = self.report("--max-lines", "3")
        self.assertEqual(d["size"]["generated_left_out"], 2)
        self.assertEqual(d["size"]["changed_lines"], 4)  # a.rb 3 + .gitattributes 1
        self.assertTrue(d["size"]["over"])
        text = self.run_script("report", "--max-lines", "3").stdout
        self.assertIn("OVER", text)
        self.assertIn("precheck: not run on this tree", text)

    def test_stale_pair(self):
        self.write("db/migrate/001_add.rb", "x\n")
        self.assertEqual(len(self.report()["stale_generated"]), 1)
        self.write("db/schema.rb", "y\n")
        self.assertEqual(self.report()["stale_generated"], [])

    def test_inside_lock(self):
        self.write("svc.rb", "def go\n  User.transaction do\n    Faraday.get(u)\n  end\n  Faraday.post(u)\nend\n")
        self.write("svc.py", "def go():\n    with transaction.atomic():\n        requests.get(u)\n"
                             "    requests.post(u)\n")
        hits = self.report()["inside_lock"]
        self.assertEqual(len(hits), 2, hits)
        self.assertTrue(any("svc.rb:3 Faraday.get" in h for h in hits))
        self.assertTrue(any("svc.py:3 requests.get" in h for h in hits))

    def test_inside_lock_skips_test_files(self):
        self.write("spec/svc_spec.rb", "User.transaction do\n  Faraday.get(u)\nend\n")
        self.write("tests/test_svc.py", "with transaction.atomic():\n    requests.get(u)\n")
        self.assertEqual(self.report()["inside_lock"], [])

    def test_bad_max_lines_exits_2(self):
        self.config(max_lines="lots")
        r = self.run_script("report")
        self.assertEqual(r.returncode, 2)
        self.assertIn("max_lines", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class Hook(Base):
    def hook(self, payload):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return self.run_script("hook", stdin=stdin)

    def push(self, cmd="git push"):
        return {"tool_input": {"command": cmd}, "cwd": str(self.repo)}

    def commit(self):
        sh(self.repo, "git", "add", ".")
        sh(self.repo, "git", "commit", "-qm", "change")

    def test_hook_timeout_is_under_the_hook_limit(self):
        self.assertLess(P.HOOK_TIMEOUT, 120)
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.commit()
        seen = []
        with mock.patch.object(P, "run_cmd", side_effect=lambda c, d, t=P.TIMEOUT: seen.append(t) or ("ok", 0, "")), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(self.push()))):
            self.assertEqual(P.cmd_hook(), 0)
        self.assertEqual(seen, [P.HOOK_TIMEOUT])

    def test_non_push_ignored(self):
        r = self.hook({"tool_input": {"command": "git status"}, "cwd": str(self.repo)})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_blocks_failing_rb_check_only_hook_langs(self):
        self.write("pyproject.toml", "")
        self.write("lib/x.py", "x\n")
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.commit()
        self.rc("rbcheck", 1)
        r = self.hook(self.push(f"git -C {self.repo} push origin feature"))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("offense from rbcheck", r.stderr)
        names = [c.split()[0] for c in self.calls()]
        self.assertEqual(names, ["rbcheck"])  # no fix, no tests, no py

    def test_tool_error_does_not_block(self):
        self.write("app/models/user.rb", "class User\n  x\nend\n")
        self.commit()
        self.rc("rbcheck", 2)
        r = self.hook(self.push())
        self.assertEqual(r.returncode, 0)
        self.assertIn("push not blocked", r.stderr)

    def test_bad_json_fails_open(self):
        r = self.hook("not json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
