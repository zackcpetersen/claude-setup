"""Tests for bin/tidy. Run: python3 -m pytest bin/tests/test_tidy.py (or python3 -m unittest ...)

Every test works in a temp folder with temp git repos and a temp origin. Nothing
touches the real home folder, and `gh` and `ps` are mocked.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("tidy", str(BIN / "tidy"))
_spec = importlib.util.spec_from_loader("tidy", _loader)
T = importlib.util.module_from_spec(_spec)
_loader.exec_module(T)

OLD = int(time.time()) - 60 * T.DAY  # older than every age limit


def sh(cwd, *args, when=OLD):
    env = {**os.environ, "GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        gitcfg = self.home / "gitconfig"
        gitcfg.write_text("[user]\n\tname = T\n\temail = t@example.invalid\n[init]\n\tdefaultBranch = main\n")
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(gitcfg), "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.prs, self.procs, self.pr_states, self.cwds = {}, [], {}, []
        for name, fake in (("gh_pr_list", self.fake_prs), ("ps_lines", lambda: list(self.procs)),
                           ("process_cwds", lambda: None if self.cwds is None else list(self.cwds)),
                           ("gh_pr_state", lambda repo, n: self.pr_states.get(str(n), "MERGED"))):
            p = mock.patch.object(T, name, side_effect=fake)
            p.start()
            self.addCleanup(p.stop)

        self.origin = self.home / "origin.git"
        sh(self.home, "git", "init", "--bare", "-b", "main", str(self.origin))
        self.repo = self.home / "Projects" / "app"
        sh(self.home, "git", "clone", "-q", str(self.origin), str(self.repo))
        (self.repo / "README.md").write_text("hi\n")
        (self.repo / ".gitignore").write_text(".env*\n")
        sh(self.repo, "git", "add", ".")
        sh(self.repo, "git", "commit", "-qm", "init")
        sh(self.repo, "git", "push", "-q", "origin", "main")
        (self.repo / "CLAUDE.md").write_text("main notes\n")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text("{}\n")
        (self.repo / ".git" / "info" / "exclude").write_text("CLAUDE.md\n.claude/\n")

        (self.home / "bin").mkdir()
        self.wt_cfg = self.home / "bin" / ".worktree-config.json"
        self.set_copy_dirs([{"path": ".claude", "exclude": ["worktrees"]}])
        self.claude = self.home / ".claude"
        (self.claude / "plans").mkdir(parents=True)
        self.handoffs = self.home / "handoffs"
        self.handoffs.mkdir()
        self.memory = self.home / "memory"
        self.memory.mkdir()
        self.config = self.home / "CLAUDE.md"
        self.write_config("- Never touch: ~/handoffs/keep-*, app:precious, ~/Projects/app-wt/guarded")

    def set_copy_dirs(self, dirs):
        self.wt_cfg.write_text(json.dumps({"repos": {"app": {
            "repo_path": str(self.repo), "worktree_base": str(self.home / "Projects" / "app-wt"),
            "default_branch": "main", "setup": {"copy_files": ["CLAUDE.md"], "copy_directories": dirs},
        }}}))

    def write_config(self, extra=""):
        # The Worktree config line is copied from the real format: backticks around each part.
        self.config.write_text(f"""# Config

## Handoffs
- Handoff folder: ~/handoffs/

### Work board (`board` skill)
- Worktree config: `~/bin/.worktree-config.json`; scripts: `~/bin/worktree`, `~/bin/start-ticket`
- Memory dir: ~/memory/

### Watches (`watch` skill)
- Slack poll state file: ~/.claude/slack-poll.json

### Tidy (`tidy` skill)
- Weekly: Fri
- Branch age: 30
{extra}

### Finalize PR (`/pr`)
- Not: part of tidy
""")
        self.cfg = T.load_config(self.config, self.home)

    def fake_prs(self, repo_path, branch=None):
        index = {}
        for pr in self.prs.values():
            if branch is None or pr["headRefName"] == branch:
                index.setdefault(pr["headRefName"], []).append(pr)
        return index

    def pr(self, n, branch, sha, state="MERGED", base="main"):
        self.prs[n] = {"number": n, "state": state, "headRefName": branch, "headRefOid": sha, "baseRefName": base}

    def branch(self, name, commit=True, when=OLD, push=False):
        sh(self.repo, "git", "branch", name, "main", when=when)
        if commit:
            sh(self.repo, "git", "checkout", "-q", name, when=when)
            (self.repo / f"{name}.txt").write_text(name)
            sh(self.repo, "git", "add", f"{name}.txt", when=when)
            sh(self.repo, "git", "commit", "-qm", name, when=when)
            if push:
                sh(self.repo, "git", "push", "-q", "-u", "origin", name, when=when)
            sh(self.repo, "git", "checkout", "-q", "main", when=when)
        return sh(self.repo, "git", "rev-parse", name)

    def merge_on_origin(self, name):
        """Merge `name` into origin/main from a second clone, leaving the local main behind."""
        other = self.home / "other"
        if not other.exists():
            sh(self.home, "git", "clone", "-q", str(self.origin), str(other))
        sh(self.repo, "git", "push", "-q", "origin", name)
        sh(other, "git", "pull", "-q", "origin", "main")
        sh(other, "git", "fetch", "-q", "origin", name)
        sh(other, "git", "merge", "-q", "--no-ff", "-m", "merge", "FETCH_HEAD")
        sh(other, "git", "push", "-q", "origin", "main")

    def scan(self, mode="weekly"):
        return T.scan(self.cfg, mode, fetch=True)["findings"]

    def find(self, findings, **kw):
        return [f for f in findings if all(f.get(k) == v for k, v in kw.items())]

    def apply(self, items, mode="weekly", dry=False):
        return T.apply(self.cfg, items, mode, dry=dry)

    def has_branch(self, name):
        return sh(self.repo, "git", "branch", "--list", name) != ""

    def log(self):
        return [json.loads(l) for l in (self.claude / "tidy" / "log.jsonl").read_text().splitlines()]


class TestConfig(Base):
    def test_backticked_worktree_config_line_finds_repos(self):
        self.assertEqual(self.cfg["worktree_config"], self.wt_cfg)
        repos, errors = T.load_repos(self.cfg)
        self.assertEqual(([r["key"] for r in repos], errors), (["app"], []))

    def test_missing_worktree_config_is_loud(self):
        self.wt_cfg.unlink()
        result = T.scan(self.cfg, "daily", fetch=False)
        self.assertTrue(result["errors"])
        self.assertTrue(self.find(result["findings"], kind="config_error"))
        out = subprocess.run([str(BIN / "tidy"), "scan", "--mode", "daily", "--no-fetch", "--config", str(self.config),
                              "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("worktree config", out.stderr)

    def test_missing_claude_md_exits_2(self):
        out = subprocess.run([str(BIN / "tidy"), "scan", "--mode", "daily", "--no-fetch", "--config",
                              str(self.home / "nope.md"), "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("cannot read config", out.stderr)

    def test_reads_sections_and_defaults(self):
        self.assertTrue(self.cfg["enabled"])
        self.assertEqual(self.cfg["handoffs"], self.home / "handoffs")
        self.assertEqual(self.cfg["memory_dir"], self.home / "memory")
        self.assertEqual(self.cfg["ages"]["Plan age"], 14)
        self.assertIn(str(self.home / "handoffs" / "keep-*"), self.cfg["never_touch"])

    def test_bad_age_is_an_error(self):
        with self.assertRaises(T.TidyError):
            self.write_config("- Plan age: soon")

    def test_cli_scan_json_runs(self):
        out = subprocess.run([str(BIN / "tidy"), "scan", "--mode", "stale", "--json", "--no-fetch",
                              "--config", str(self.config), "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["mode"], "stale")


class TestMergedRule(Base):
    def test_merged_by_ancestry_is_tier1(self):
        self.branch("feat-a")
        self.merge_on_origin("feat-a")
        hits = self.find(self.scan("daily"), branch="feat-a")
        self.assertEqual([(h["tier"], h["kind"], h["merged_by"]) for h in hits], [(1, "delete_branch", "ancestor")])

    def test_local_main_behind_origin_still_detects_merged(self):
        self.branch("feat-b")
        self.merge_on_origin("feat-b")
        found = self.scan("daily")
        self.assertNotEqual(sh(self.repo, "git", "rev-parse", "main"), sh(self.repo, "git", "rev-parse", "origin/main"))
        self.assertEqual(self.find(found, branch="feat-b")[0]["tier"], 1)

    def test_squash_merged_with_matching_pr_head_is_tier1(self):
        sha = self.branch("feat-sq", push=True)
        self.pr(1, "feat-sq", sha)
        hits = self.find(self.scan("daily"), branch="feat-sq")
        self.assertEqual([(h["tier"], h["merged_by"]) for h in hits], [(1, "pr")])

    def test_pr_merged_into_another_base_is_not_merged(self):
        sha = self.branch("feat-base", push=True)
        self.pr(1, "feat-base", sha, base="release")
        self.assertFalse([h for h in self.find(self.scan(), branch="feat-base") if h["tier"] == 1])

    def test_tip_moved_after_pr_head_is_not_tier1(self):
        old = self.branch("feat-moved")
        self.pr(2, "feat-moved", old)
        sh(self.repo, "git", "checkout", "-q", "feat-moved")
        (self.repo / "more.txt").write_text("more")
        sh(self.repo, "git", "add", "more.txt")
        sh(self.repo, "git", "commit", "-qm", "more")
        sh(self.repo, "git", "checkout", "-q", "main")
        self.assertFalse([h for h in self.find(self.scan(), branch="feat-moved") if h["tier"] == 1])

    def test_fresh_branch_on_main_tip_is_not_offered(self):
        self.branch("just-made", commit=False, when=int(time.time()))
        self.assertEqual(self.find(self.scan(), branch="just-made"), [])

    def test_old_branch_with_no_own_commits_is_never_tier1(self):
        self.branch("no-commits", commit=False)
        sha = sh(self.repo, "git", "rev-parse", "no-commits")
        self.pr(4, "no-commits", "f" * 40, state="CLOSED")
        hits = self.find(self.scan(), branch="no-commits")
        self.assertFalse([h for h in hits if h["tier"] == 1], hits)
        wt = self.home / "wt-plan"
        sh(self.repo, "git", "branch", "waiting", sha)
        sh(self.repo, "git", "worktree", "add", "-q", str(wt), "waiting")
        self.assertEqual(self.find(self.scan(), branch="waiting"), [])

    def test_open_pr_branch_never_offered(self):
        sha = self.branch("feat-open")
        self.merge_on_origin("feat-open")
        self.pr(3, "feat-open", sha, state="OPEN")
        self.assertEqual(self.find(self.scan(), branch="feat-open"), [])


class TestBranchTiers(Base):
    def test_gone_upstream_unmerged_branch_is_tier2(self):
        self.branch("feat-gone", push=True)
        sh(self.repo, "git", "push", "-q", "origin", "--delete", "feat-gone")
        hits = self.find(self.scan(), branch="feat-gone")
        self.assertEqual([(h["tier"], h["kind"], h["reason"]) for h in hits], [(2, "branch_gone", "upstream gone")])

    def test_gone_branch_not_offered_in_daily(self):
        self.branch("feat-gone2", push=True)
        sh(self.repo, "git", "push", "-q", "origin", "--delete", "feat-gone2")
        self.assertEqual(self.find(self.scan("daily"), branch="feat-gone2"), [])

    def test_old_no_pr_branches_batched_oldest_first(self):
        self.branch("older", when=OLD - 10 * T.DAY)
        self.branch("newer", when=OLD)
        hits = self.find(self.scan(), kind="branch_no_pr")
        self.assertEqual([h["branch"] for h in hits], ["older", "newer"])
        self.assertEqual({h["batch"] for h in hits}, {1})

    def test_checked_out_and_default_branches_never_offered(self):
        self.branch("feat-co")
        self.merge_on_origin("feat-co")
        sh(self.repo, "git", "checkout", "-q", "feat-co")
        found = self.scan()
        self.assertEqual(self.find(found, branch="feat-co"), [])
        self.assertEqual(self.find(found, branch="main"), [])

    def test_worktree_markers_are_not_parsed_into_names(self):
        self.branch("feat-wt")
        self.merge_on_origin("feat-wt")
        sh(self.repo, "git", "worktree", "add", "-q", str(self.home / "wt-a"), "feat-wt")
        names = {f.get("branch") for f in self.scan()}
        self.assertFalse({n for n in names if n and n[0] in "+*"})
        self.assertIn("feat-wt", names)

    def test_unmerged_delete_keeps_commits_and_restores(self):
        sha = self.branch("feat-keep", push=True)
        sh(self.repo, "git", "push", "-q", "origin", "--delete", "feat-keep")
        item = self.find(self.scan(), branch="feat-keep")[0]
        res = self.apply([item])
        self.assertEqual(res[0]["status"], "done", res)
        self.assertFalse(self.has_branch("feat-keep"))
        self.assertEqual(sh(self.repo, "git", "rev-parse", f"refs/tidy-archive/{sha}"), sha)
        self.assertIn("refs/tidy-archive", res[0]["detail"])
        subprocess.run(res[0]["restore"], shell=True, check=True)
        self.assertEqual(sh(self.repo, "git", "rev-parse", "feat-keep"), sha)

    def test_squash_merged_delete_keeps_commits(self):
        sha = self.branch("feat-sq2", push=True)
        self.pr(9, "feat-sq2", sha)
        res = self.apply(self.find(self.scan("daily"), branch="feat-sq2"), "daily")
        self.assertEqual(res[0]["status"], "done", res)
        self.assertEqual(sh(self.repo, "git", "rev-parse", f"refs/tidy-archive/{sha}"), sha)


class TestWorktrees(Base):
    def make_wt(self, name="feat-w", where=None):
        self.branch(name)
        self.merge_on_origin(name)
        wt = where or self.home / "Projects" / "app-wt" / name
        sh(self.repo, "git", "worktree", "add", "-q", str(wt), name)
        (wt / "CLAUDE.md").write_text((self.repo / "CLAUDE.md").read_text())
        (wt / ".claude").mkdir()
        (wt / ".claude" / "settings.json").write_text("{}\n")
        return wt

    def test_byte_identical_setup_copies_are_clean(self):
        wt = self.make_wt()
        hits = self.find(self.scan("daily"), branch="feat-w")
        self.assertEqual([(h["tier"], h["kind"], h["path"]) for h in hits], [(1, "remove_worktree", str(wt))])

    def test_edited_ignored_copy_is_a_real_edit(self):
        wt = self.make_wt()
        (wt / "CLAUDE.md").write_text("my own notes\n")
        hits = self.find(self.scan("daily"), branch="feat-w")
        self.assertEqual([(h["tier"], h["kind"]) for h in hits], [("report", "worktree_edits")])
        self.assertIn("CLAUDE.md", hits[0]["files"])

    def test_untracked_file_inside_copied_folder_is_a_real_edit(self):
        wt = self.make_wt()
        (wt / ".claude" / "notes.md").write_text("new\n")
        hits = self.find(self.scan("daily"), branch="feat-w")
        self.assertEqual(hits[0]["kind"], "worktree_edits")
        self.assertIn(".claude/notes.md", hits[0]["files"])

    def test_excluded_path_in_copied_folder_is_not_a_real_edit(self):
        wt = self.make_wt()
        (wt / ".claude" / "worktrees").mkdir()
        (wt / ".claude" / "worktrees" / "x.txt").write_text("own\n")
        self.assertEqual(self.find(self.scan("daily"), branch="feat-w")[0]["kind"], "remove_worktree")

    def test_clean_tracked_file_in_copied_folder_that_differs_from_main_is_not_an_edit(self):
        sh(self.repo, "git", "checkout", "-q", "-b", "feat-tr")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "a.md").write_text("branch version\n")
        sh(self.repo, "git", "add", "docs/a.md")
        sh(self.repo, "git", "commit", "-qm", "docs")
        sh(self.repo, "git", "checkout", "-q", "main")
        self.set_copy_dirs(["docs"])
        self.merge_on_origin("feat-tr")
        sh(self.repo, "git", "worktree", "add", "-q", str(self.home / "wt-tr"), "feat-tr")
        self.assertEqual([h["kind"] for h in self.find(self.scan("daily"), branch="feat-tr")], ["remove_worktree"])

    def test_ignored_non_copy_file_blocks_tier1(self):
        wt = self.make_wt()
        (wt / ".env.local").write_text("SECRET=1\n")
        self.assertEqual(self.find(self.scan("daily"), branch="feat-w"), [])
        hits = self.find(self.scan(), branch="feat-w")
        self.assertEqual([(h["tier"], h["kind"], h["ignored"]) for h in hits], [(2, "remove_worktree", [".env.local"])])

    def test_ignored_file_appearing_after_scan_skips_apply(self):
        wt = self.make_wt()
        item = self.find(self.scan("daily"), branch="feat-w")[0]
        (wt / ".env.local").write_text("SECRET=1\n")
        res = self.apply([item], "daily")
        self.assertEqual(res[0]["status"], "skipped")
        self.assertTrue(wt.exists())

    def test_real_edit_appearing_after_scan_skips_apply(self):
        wt = self.make_wt()
        item = self.find(self.scan("daily"), branch="feat-w")[0]
        (wt / "new.py").write_text("x")
        res = self.apply([item], "daily")
        self.assertTrue(res[0]["detail"].startswith("worktree has real edits"), res)
        self.assertTrue(wt.exists())

    def test_apply_removes_worktree_and_restore_keeps_custom_path(self):
        wt = self.make_wt(where=self.home / "custom-place")
        items = self.find(self.scan("daily"), kind="remove_worktree")
        res = self.apply(items, "daily")
        self.assertEqual(res[0]["status"], "done", res)
        self.assertFalse(wt.exists())
        self.assertFalse(self.has_branch("feat-w"))
        self.assertIn("main fast-forwarded", res[0]["detail"])
        self.assertIn("not restored", res[0]["restore"])
        subprocess.run(res[0]["restore"], shell=True, check=True)
        self.assertTrue((wt / "feat-w.txt").exists())

    def test_worktree_with_live_process_is_not_removed(self):
        wt = self.make_wt()
        self.cwds = [str(wt / ".claude")]
        hits = self.find(self.scan("daily"), branch="feat-w")
        self.assertEqual([(h["tier"], h["kind"]) for h in hits], [("report", "worktree_in_use")])
        self.cwds = None
        self.assertEqual(self.find(self.scan("daily"), branch="feat-w")[0]["kind"], "worktree_in_use")

    def test_process_starting_in_worktree_after_scan_skips_apply(self):
        wt = self.make_wt()
        item = self.find(self.scan("daily"), branch="feat-w")[0]
        self.cwds = [str(wt)]
        res = self.apply([item], "daily")
        self.assertTrue(res[0]["detail"].startswith("worktree in use"), res)
        self.assertTrue(wt.exists())

    def test_ignored_recheck_compares_full_list_and_count(self):
        wt = self.make_wt()
        for i in range(21):
            (wt / f".env.{i:02d}").write_text("x")
        item = self.find(self.scan(), branch="feat-w")[0]
        self.assertEqual((len(item["ignored"]), item["ignored_count"]), (21, 21))
        (wt / ".env.99").write_text("late")
        self.assertEqual(self.apply([item])[0]["status"], "skipped")
        (wt / ".env.99").unlink()
        self.assertEqual(self.apply([{**item, "ignored": item["ignored"][:20]}])[0]["status"], "skipped")
        self.assertEqual(self.apply([item])[0]["status"], "done")

    def test_worktree_moved_or_gone_skipped(self):
        wt = self.make_wt()
        item = self.find(self.scan("daily"), branch="feat-w")[0]
        res = self.apply([{**item, "path": str(self.home / "elsewhere"), "target": "x"}], "daily")
        self.assertEqual(res[0]["detail"], "worktree moved or gone")
        self.assertTrue(wt.exists())

    def test_nested_worktree_blocks_scan_and_apply(self):
        wt = self.make_wt()
        item = self.find(self.scan("daily"), branch="feat-w")[0]
        self.branch("inner")
        sh(self.repo, "git", "worktree", "add", "-q", str(wt / ".claude" / "worktrees" / "inner"), "inner")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "another worktree lives inside it")
        self.assertEqual(self.find(self.scan("daily"), branch="feat-w")[0]["kind"], "worktree_edits")

    def test_never_touch_protects_worktree_path(self):
        self.make_wt(name="guarded")
        self.assertEqual(self.find(self.scan("daily"), branch="guarded"), [])


class TestApplyGuards(Base):
    def merged_item(self, name="feat-x"):
        self.branch(name)
        self.merge_on_origin(name)
        return self.find(self.scan("daily"), branch=name)[0]

    def test_skips_item_whose_sha_changed(self):
        item = self.merged_item()
        sh(self.repo, "git", "checkout", "-q", "feat-x")
        (self.repo / "late.txt").write_text("late")
        sh(self.repo, "git", "add", "late.txt")
        sh(self.repo, "git", "commit", "-qm", "late")
        sh(self.repo, "git", "checkout", "-q", "main")
        res = self.apply([item], "daily")
        self.assertEqual((res[0]["status"], res[0]["detail"]), ("skipped", "branch tip changed since the scan"))
        self.assertTrue(self.has_branch("feat-x"))

    def test_default_branch_refused(self):
        item = self.merged_item()
        item.update(branch="main", sha=sh(self.repo, "git", "rev-parse", "main"))
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "default branch")

    def test_main_checkout_branch_skipped(self):
        item = self.merged_item()
        sh(self.repo, "git", "checkout", "-q", "feat-x")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "checked out in the main checkout")

    def test_branch_checked_out_in_worktree_skipped(self):
        item = self.merged_item()
        sh(self.repo, "git", "worktree", "add", "-q", str(self.home / "wt-x"), "feat-x")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "checked out in a worktree")

    def test_open_pr_after_scan_skipped(self):
        item = self.merged_item()
        self.pr(5, "feat-x", item["sha"], state="OPEN")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "PR is open")

    def test_no_longer_proven_merged_skipped(self):
        sha = self.branch("feat-pr", push=True)
        self.pr(6, "feat-pr", sha)
        item = self.find(self.scan("daily"), branch="feat-pr")[0]
        self.pr(6, "feat-pr", sha, base="release")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "no longer proven merged")
        self.assertTrue(self.has_branch("feat-pr"))

    def test_gh_unavailable_at_apply_skips(self):
        item = self.merged_item()
        with mock.patch.object(T, "gh_pr_list", return_value=None):
            self.assertEqual(self.apply([item], "daily")[0]["detail"], "cannot check the PR right now")
        self.assertTrue(self.has_branch("feat-x"))

    def test_repo_not_in_config_refused(self):
        item = self.merged_item()
        res = self.apply([{**item, "repo_path": str(self.home / "other-repo")}], "daily")
        self.assertEqual((res[0]["status"], res[0]["detail"]),
                         ("refused", "repo is not in the worktree config or Extra repos"))

    def test_remove_empty_no_longer_empty_and_already_gone(self):
        d = self.claude / "plans" / "empty"
        d.mkdir()
        item = self.find(self.scan("daily"), path=str(d))[0]
        (d / "x.md").write_text("now has content")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "no longer empty")
        (d / "x.md").unlink()
        d.rmdir()
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "already gone")

    def test_trim_already_short_skipped(self):
        log = self.claude / "slack-poll-triage.jsonl"
        log.write_text("".join(f"{i}\n" for i in range(700)))
        item = self.find(self.scan("daily"), kind="trim_log")[0]
        log.write_text("short\n")
        self.assertEqual(self.apply([item], "daily")[0]["detail"], "already short")

    def test_restore_command_recreates_branch_at_same_sha(self):
        item = self.merged_item()
        res = self.apply([item], "daily")
        self.assertEqual(res[0]["status"], "done")
        self.assertFalse(self.has_branch("feat-x"))
        subprocess.run(res[0]["restore"], shell=True, check=True)
        self.assertEqual(sh(self.repo, "git", "rev-parse", "feat-x"), item["sha"])

    def test_intent_logged_before_act_and_failure_logged_after(self):
        plan = self.claude / "plans" / "p.md"
        plan.write_text("p")
        os.utime(plan, (OLD, OLD))
        item = self.find(self.scan(), path=str(plan))[0]
        with mock.patch.object(T.shutil, "move", side_effect=OSError("disk full")):
            res = self.apply([item])
        self.assertEqual(res[0]["status"], "failed")
        log = self.log()
        self.assertEqual([(l["phase"], l.get("result")) for l in log], [("intent", None), ("result", "failed")])
        self.assertTrue(log[0]["restore"].startswith("mv "))

    def test_never_touch_by_path_with_dotdot_and_by_repo_branch(self):
        keep = self.handoffs / "keep-me.md"
        keep.write_text("x")
        sneaky = str(self.handoffs / "sub" / ".." / "keep-me.md")
        item = {"tier": 2, "kind": "archive_file", "target": sneaky, "path": sneaky, "mtime": 0}
        self.assertEqual(self.apply([item])[0]["detail"], "matches Never touch")
        self.branch("precious")
        self.merge_on_origin("precious")
        self.assertEqual(self.find(self.scan(), branch="precious"), [])

    def test_never_touch_path_not_in_scan(self):
        keep = self.handoffs / "keep-old.md"
        keep.write_text("x")
        os.utime(keep, (OLD, OLD))
        (self.handoffs / "newest.md").write_text("n")
        self.assertEqual(self.find(self.scan(), path=str(keep)), [])

    def test_refuses_tier3_report_and_unknown_paths(self):
        outside = self.home / "elsewhere.txt"
        outside.write_text("x")
        items = [{"tier": "report", "kind": "dirty_checkout", "target": "app"},
                 {"tier": 2, "kind": "archive_file", "target": str(outside), "path": str(outside), "mtime": 0},
                 {"tier": 2, "kind": "archive_file", "target": "m", "path": str(self.memory / "MEMORY.md"), "mtime": 0}]
        self.assertEqual([r["status"] for r in self.apply(items)], ["refused"] * 3)
        self.assertTrue(outside.exists())

    def test_under_rejects_traversal_and_symlinked_parent(self):
        roots = T.known_roots(self.cfg)
        self.assertFalse(T.under(self.claude / "plans" / ".." / "settings.json", roots))
        self.assertFalse(T.under(self.claude / "plans" / ".." / ".." / "elsewhere.txt", roots))
        os.symlink(self.home, self.claude / "plans" / "escape")
        self.assertFalse(T.under(self.claude / "plans" / "escape" / "elsewhere.txt", roots))
        self.assertTrue(T.under(self.claude / "plans" / "a.md", roots))

    def test_free_never_overwrites(self):
        a = self.home / "a.txt"
        a.write_text("1")
        (self.home / "a.txt.1").write_text("2")
        self.assertEqual(T.free(a), self.home / "a.txt.2")
        self.assertEqual(T.free(self.home / "b.txt"), self.home / "b.txt")

    def test_dest_and_index_lines_from_input_are_ignored(self):
        plan = self.claude / "plans" / "p.md"
        plan.write_text("p")
        os.utime(plan, (OLD, OLD))
        item = self.find(self.scan(), path=str(plan))[0]
        item["dest"] = str(self.home / "stolen.md")
        item["index_lines"] = ["- [x](y.md)"]
        res = self.apply([item])
        self.assertEqual(res[0]["status"], "done")
        self.assertFalse((self.home / "stolen.md").exists())
        self.assertIn(str(self.claude / "tidy" / "archive"), res[0]["detail"])

    def test_archive_without_mtime_refused(self):
        plan = self.claude / "plans" / "p.md"
        plan.write_text("p")
        item = {"tier": 2, "kind": "archive_file", "target": str(plan), "path": str(plan)}
        self.assertEqual(self.apply([item])[0]["status"], "refused")

    def test_dry_run_changes_nothing_and_writes_no_state(self):
        item = self.merged_item()
        old_plan = self.claude / "plans" / "old.md"
        old_plan.write_text("plan")
        os.utime(old_plan, (OLD, OLD))
        items = [item] + self.find(self.scan(), path=str(old_plan))
        res = self.apply(items, dry=True)
        self.assertEqual([r["status"] for r in res], ["would", "would"], res)
        self.assertTrue(self.has_branch("feat-x"))
        self.assertTrue(old_plan.exists())
        self.assertFalse((self.claude / "tidy").exists())

    def test_real_run_writes_state(self):
        self.apply([])
        self.assertIn("last_weekly", json.loads((self.claude / "tidy" / "state.json").read_text()))
        self.assertFalse(T.scan(self.cfg, "stale")["weekly_due"])

    def test_refuses_without_tidy_section(self):
        self.config.write_text(self.config.read_text().replace("### Tidy", "### Other"))
        with self.assertRaises(T.TidyError):
            T.apply(T.load_config(self.config, self.home), [], "daily", dry=False)


class TestProcesses(Base):
    CMD = "python3 /x/wait-for pr acme/app 12 --sha abc"

    def test_merged_pr_wait_is_tier1_and_stops(self):
        self.procs = [(4242, self.CMD)]
        item = self.find(self.scan("daily"), kind="stop_process")[0]
        with mock.patch.object(T.os, "kill") as kill:
            res = self.apply([item], "daily")
        self.assertEqual(res[0]["status"], "done")
        kill.assert_called_once()

    def test_stop_skipped_when_command_changed_or_not_wait_for(self):
        self.procs = [(4242, self.CMD)]
        item = self.find(self.scan("daily"), kind="stop_process")[0]
        self.procs = [(4242, "vim notes.md")]
        with mock.patch.object(T.os, "kill") as kill:
            self.assertEqual(self.apply([item], "daily")[0]["status"], "skipped")
            forged = {**item, "command": "vim notes.md"}
            self.assertEqual(self.apply([forged], "daily")[0]["status"], "skipped")
        kill.assert_not_called()

    def test_stop_skipped_when_pr_reopened(self):
        self.procs = [(4242, self.CMD)]
        item = self.find(self.scan("daily"), kind="stop_process")[0]
        self.pr_states["12"] = "OPEN"
        with mock.patch.object(T.os, "kill") as kill:
            self.assertEqual(self.apply([item], "daily")[0]["status"], "skipped")
        kill.assert_not_called()


class TestFiles(Base):
    def test_empty_plan_folder_is_tier1_and_old_plan_tier2_with_registry_note(self):
        (self.claude / "plans" / "empty-dir").mkdir()
        old = self.claude / "plans" / "done.md"
        old.write_text("x")
        os.utime(old, (OLD, OLD))
        found = self.scan("stale")
        self.assertEqual(self.find(found, path=str(self.claude / "plans" / "empty-dir"))[0]["tier"], 1)
        plan = self.find(found, path=str(old))[0]
        self.assertEqual(plan["tier"], 2)
        self.assertIn("Work registry", plan["note"])

    def test_newest_handoff_and_todays_files_folder_never_offered(self):
        for name in ("a.md", "b.md"):
            (self.handoffs / name).write_text(name)
            os.utime(self.handoffs / name, (OLD, OLD))
        os.utime(self.handoffs / "b.md", (OLD + 10, OLD + 10))
        todays = self.handoffs / f"{time.strftime('%Y-%m-%d')}-files"
        todays.mkdir()
        (todays / "x.md").write_text("x")
        os.utime(todays / "x.md", (OLD, OLD))
        paths = {f["path"] for f in self.scan("stale") if f.get("bucket") == "handoff"}
        self.assertEqual(paths, {str(self.handoffs / "a.md")})

    def test_handoff_archive_goes_to_month_folder(self):
        (self.handoffs / "a.md").write_text("a")
        os.utime(self.handoffs / "a.md", (OLD, OLD))
        (self.handoffs / "new.md").write_text("n")
        item = self.find(self.scan("stale"), path=str(self.handoffs / "a.md"))[0]
        res = self.apply([item])
        self.assertEqual(res[0]["status"], "done")
        self.assertTrue(Path(item["dest"]).exists())
        self.assertIn("/archive/", item["dest"])

    def write_memory(self, name, mtype, desc, body="body\n"):
        p = self.memory / name
        p.write_text(f"---\nname: {name[:-3]}\ndescription: {desc}\nmetadata:\n  type: {mtype}\n---\n{body}")
        os.utime(p, (OLD, OLD))
        return p

    def test_finished_project_memory_archived_with_index_line_and_restorable(self):
        mem = self.write_memory("old-work.md", "project", "ENDED 10-01, all closed")
        self.write_memory("live.md", "project", "ongoing")
        index = self.memory / "MEMORY.md"
        index.write_text("- [Old](old-work.md) - ENDED\n- [Live](live.md) - ongoing\n")
        items = self.find(self.scan(), bucket="memory")
        self.assertEqual([i["path"] for i in items], [str(mem)])
        res = self.apply(items)
        self.assertEqual(index.read_text(), "- [Live](live.md) - ongoing\n")
        self.assertTrue((self.memory / "archive" / "old-work.md").exists())
        subprocess.run(res[0]["restore"], shell=True, check=True)
        self.assertTrue(mem.exists())
        self.assertIn("old-work.md", index.read_text())

    def test_memory_no_longer_finished_at_apply_skipped(self):
        mem = self.write_memory("w.md", "project", "DONE 10-01")
        item = self.find(self.scan(), bucket="memory")[0]
        mem.write_text(mem.read_text().replace("DONE 10-01", "reopened 11-19"))
        os.utime(mem, (item["mtime"], item["mtime"]))
        self.assertEqual(self.apply([item])[0]["detail"], "memory no longer reads as finished project work")
        self.assertTrue(mem.exists())

    def test_handoff_that_became_newest_is_skipped(self):
        for name, t in (("a.md", OLD), ("b.md", OLD + 10)):
            (self.handoffs / name).write_text(name)
            os.utime(self.handoffs / name, (t, t))
        item = self.find(self.scan("stale"), path=str(self.handoffs / "a.md"))[0]
        (self.handoffs / "b.md").unlink()
        self.assertEqual(self.apply([item])[0]["detail"], "newest handoff or today's files")

    def test_unlinked_skill_that_stopped_shadowing_is_skipped(self):
        repo_skills = self.home / "setup" / "skills"
        (repo_skills / "board").mkdir(parents=True)
        (self.claude / "skills").mkdir()
        os.symlink(repo_skills / "board", self.claude / "skills" / "linked")
        (self.claude / "skills" / "board").mkdir()
        (self.claude / "skills" / "board" / "SKILL.md").write_text("x")
        item = self.find(self.scan(), bucket="unlinked_skills", tier=2)[0]
        os.rename(repo_skills / "board", repo_skills / "renamed")
        self.assertEqual(self.apply([item])[0]["detail"], "no longer shadows a repo item")

    def test_rule_memories_and_word_matches_never_offered(self):
        self.write_memory("rule.md", "feedback", "Done tickets get closed by automation (Done, reopen)")
        self.write_memory("user.md", "user", "DONE with onboarding")
        self.write_memory("proj.md", "project", "Export work; phase 1 done, phase 2 open", body="Still going, closed one PR.\n")
        self.assertEqual(self.find(self.scan(), bucket="memory"), [])

    def test_triage_trim_waits_for_poll_to_stop(self):
        log = self.claude / "slack-poll-triage.jsonl"
        log.write_text("".join(f"{i}\n" for i in range(700)))
        item = self.find(self.scan("daily"), kind="trim_log")[0]
        self.procs = [(99, "python3 /x/wait-for slack")]
        self.assertEqual(self.apply([item], "daily")[0]["status"], "skipped")
        self.procs = []
        res = self.apply([item], "daily")
        self.assertEqual(res[0]["status"], "done")
        self.assertEqual(len(log.read_text().splitlines()), T.TRIAGE_KEEP)
        subprocess.run(res[0]["restore"], shell=True, check=True)
        self.assertEqual(len(log.read_text().splitlines()), 700)

    def test_unlinked_skill_shadowing_is_tier2_others_report_only(self):
        repo_skills = self.home / "setup" / "skills"
        (repo_skills / "board").mkdir(parents=True)
        (self.claude / "skills").mkdir()
        os.symlink(repo_skills / "board", self.claude / "skills" / "linked")
        for name in ("board", "mine"):
            (self.claude / "skills" / name).mkdir()
            (self.claude / "skills" / name / "SKILL.md").write_text("x")
        (self.claude / "skills" / "old.bak").mkdir()
        items = self.find(self.scan(), bucket="unlinked_skills")
        self.assertEqual(sorted((Path(i["target"]).name, i["tier"]) for i in items),
                         [("board", 2), ("mine", "report")])


if __name__ == "__main__":
    unittest.main()
