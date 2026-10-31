"""Tests for bin/wait-for. Run: python3 -m pytest bin/tests/test_wait_for.py"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("wait_for", str(BIN / "wait-for"))
_spec = importlib.util.spec_from_loader("wait_for", _loader)
W = importlib.util.module_from_spec(_spec)
_loader.exec_module(W)

CFG_MD = """# Machine config

### Watches (`watch` skill)
<!-- FILL IN: values for the watch skill. -->
- Time zone: America/Denver
- Business hours: 08:00-18:00
- Connectors: slack mcp__slack__
- Dagster: https://example.invalid/graphql, env file {tmp}/.env, token var DAGSTER_TOKEN
- Deploy rules: <!-- one line per repo -->
  - acme/app: branch prod
  - acme/web: workflow deploy on main
  - acme/lib: release-tag

### Finalize PR (`/pr`)
- Not: part of the section
"""

H1, H2 = "a" * 40, "b" * 40
OK = {"status": "COMPLETED", "conclusion": "SUCCESS", "name": "build"}
BAD = {"status": "COMPLETED", "conclusion": "FAILURE", "name": "lint"}
PENDING = {"status": "IN_PROGRESS", "conclusion": None, "name": "slow"}


def view(**kw):
    base = {"state": "OPEN", "headRefOid": H1, "reviewDecision": "APPROVED", "statusCheckRollup": [OK],
            "mergeStateStatus": "CLEAN", "mergeCommit": None}
    base.update(kw)
    return base


def fake_cmd(table):
    """run_cmd stand-in: the first table key found in the joined args picks the output."""
    calls = []

    def run(args):
        calls.append(list(args))
        joined = " ".join(args)
        for key, out in table.items():
            if key in joined:
                if isinstance(out, Exception):
                    raise out
                return out if isinstance(out, str) else json.dumps(out)
        raise AssertionError(f"unexpected command {args}")

    return run, calls


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.cfg_path = self.tmp / "CLAUDE.md"
        self.cfg_path.write_text(CFG_MD.format(tmp=self.tmp))
        self.cfg = W.load_config(self.cfg_path)
        self.now = 0.0
        self.sleeps = []

        def sleep(s):
            self.sleeps.append(s)
            self.now += s

        for target, repl in (("SLEEP", sleep), ("CLOCK", lambda: self.now)):
            p = mock.patch.object(W, target, repl)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("DAGSTER_TOKEN", None)

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = W.main([*argv, "--config", str(self.cfg_path)])
            except SystemExit as e:  # argparse usage errors
                rc = e.code
        return rc, out.getvalue().strip(), err.getvalue()

    def run_with(self, table, *argv):
        run, calls = fake_cmd(table)
        with mock.patch.object(W, "run_cmd", side_effect=run):
            result = self.main(*argv)
        return result + (calls,)


class ConfigTests(Base):
    def test_load_config_kept_lines(self):
        self.assertEqual(self.cfg["deploy_rules"]["acme/web"], {"type": "workflow", "name": "deploy", "branch": "main"})
        self.assertEqual(self.cfg["deploy_rules"]["acme/app"], {"type": "branch", "name": "prod"})
        self.assertEqual(self.cfg["deploy_rules"]["acme/lib"], {"type": "release-tag"})
        self.assertEqual(len(self.cfg["deploy_rules"]), 3)
        self.assertEqual(
            self.cfg["dagster"],
            {"url": "https://example.invalid/graphql", "env_file": str(self.tmp / ".env"), "token_var": "DAGSTER_TOKEN"},
        )

    def test_backticked_values_are_unwrapped(self):
        self.cfg_path.write_text(CFG_MD.format(tmp=self.tmp).replace("  - acme/app: branch prod", "  - `acme/app`: `branch prod`"))
        self.assertEqual(W.load_config(self.cfg_path)["deploy_rules"]["acme/app"], {"type": "branch", "name": "prod"})

    def test_angle_bracketed_dagster_fields_are_unwrapped(self):
        text = CFG_MD.format(tmp=self.tmp).replace(
            f"Dagster: https://example.invalid/graphql, env file {self.tmp}/.env, token var DAGSTER_TOKEN",
            f"Dagster: <https://example.invalid/graphql>, env file <{self.tmp}/.env>, token var <DAGSTER_TOKEN>",
        )
        self.cfg_path.write_text(text)
        self.assertEqual(W.load_config(self.cfg_path)["dagster"]["token_var"], "DAGSTER_TOKEN")

    def test_template_placeholder_in_dagster_names_the_line(self):
        text = CFG_MD.format(tmp=self.tmp).replace(
            f"Dagster: https://example.invalid/graphql, env file {self.tmp}/.env, token var DAGSTER_TOKEN",
            "Dagster: <https://<org>.dagster.cloud/<deployment>/graphql>, env file <~/path/to/.env>, token var <DAGSTER_CLOUD_API_TOKEN>",
        )
        self.cfg_path.write_text(text)
        with self.assertRaisesRegex(W.WaitError, "`Dagster` line .* template placeholder"):
            W.load_config(self.cfg_path)
        rc, out, err, _ = self.run_with({}, "dagster", "run", "r1")
        self.assertEqual(rc, 2)
        self.assertIn("`Dagster` line", err)

    def test_shipped_template_watches_block_parses(self):
        template = BIN.parent / "claude-md" / "CLAUDE.md.template"
        lines = [l for l in template.read_text().splitlines() if not l.startswith("- Dagster:")]
        self.cfg_path.write_text("\n".join(lines))
        self.assertIsNone(W.load_config(self.cfg_path)["dagster"])

    def test_missing_config_file_exits_2(self):
        rc, out, err, _ = self.run_with({}, "pr", "acme/app", "1")
        self.assertEqual(rc, 0)  # pr mode never reads the config
        self.cfg_path.unlink()
        rc, out, err, _ = self.run_with({}, "deploy", "acme/app", "s1")
        self.assertEqual(rc, 2)
        self.assertIn("cannot read config", err)

    def test_parse_duration(self):
        self.assertEqual(W.parse_duration("5m"), timedelta(minutes=5))
        self.assertEqual(W.parse_duration("2h"), timedelta(hours=2))
        self.assertEqual(W.parse_duration("30s"), timedelta(seconds=30))
        self.assertEqual(W.parse_duration("1d"), timedelta(days=1))
        with self.assertRaises(W.WaitError):
            W.parse_duration("soon")

    def test_parse_deploy_rule_grammar(self):
        self.assertEqual(W.parse_deploy_rule("release-tag"), {"type": "release-tag"})
        self.assertEqual(W.parse_deploy_rule("branch prod"), {"type": "branch", "name": "prod"})
        with self.assertRaises(W.WaitError):
            W.parse_deploy_rule("tag v1")


class RollupTests(unittest.TestCase):
    def test_rollup_state_cases(self):
        ok = {"status": "COMPLETED", "conclusion": "SUCCESS"}
        self.assertEqual(W.rollup_state([ok], "BLOCKED"), "green")
        self.assertEqual(W.rollup_state([ok, {"status": "COMPLETED", "conclusion": "FAILURE"}], "BLOCKED"), "failed")
        self.assertEqual(W.rollup_state([{"status": "COMPLETED", "conclusion": "CANCELLED"}], "BLOCKED"), "failed")
        self.assertEqual(W.rollup_state([{"status": "IN_PROGRESS", "conclusion": None}], "BLOCKED"), "pending")
        self.assertEqual(W.rollup_state([{"state": "ERROR"}], "UNSTABLE"), "failed")
        self.assertEqual(W.rollup_state([ok, {"state": "PENDING"}], "BLOCKED"), "pending")
        self.assertEqual(W.rollup_state([{"state": "SUCCESS"}], "BLOCKED"), "green")
        self.assertEqual((W.rollup_state([], "CLEAN"), W.rollup_state([], "BLOCKED")), ("green", "pending"))


class PrTests(Base):
    def pr(self, v, *extra, checks=None):
        table = {"pr view": v}
        if checks is not None:
            table["pr checks"] = checks
        rc, out, err, calls = self.run_with(table, "pr", "acme/app", "7", *extra)
        self.assertEqual(rc, 0, err)
        return out

    def test_ready_approved_clean(self):
        self.assertEqual(self.pr(view()), f"READY 7 {H1} approved")

    def test_ready_no_review_required_when_decision_empty(self):
        for empty in ("", None):
            self.assertEqual(self.pr(view(reviewDecision=empty)), f"READY 7 {H1} no-review-required")

    def test_ready_unstable_lists_failed_optional_checks(self):
        v = view(mergeStateStatus="UNSTABLE", statusCheckRollup=[OK, BAD])
        checks = [{"name": "build", "bucket": "pass"}]
        self.assertEqual(self.pr(v, checks=checks), f"READY 7 {H1} approved optional-failed=lint")
        # no required checks at all: gh exits non-zero, GitHub still allows the merge
        none = subprocess.CalledProcessError(1, ["gh"], stderr="no required checks reported on the 'x' branch")
        self.assertEqual(self.pr(v, checks=none), f"READY 7 {H1} approved optional-failed=lint")

    def test_ready_does_not_append_empty_optional_list(self):
        self.assertEqual(self.pr(view(mergeStateStatus="UNSTABLE")), f"READY 7 {H1} approved")

    def test_pending_checks_block_ready(self):
        for ms in ("UNSTABLE", "CLEAN", "HAS_HOOKS"):
            self.now, self.sleeps = 0.0, []
            v = view(mergeStateStatus=ms, statusCheckRollup=[OK, PENDING])
            self.assertEqual(self.pr(v, "--max", "10m"), "TIMEOUT pr acme/app#7")

    def test_optional_failure_with_other_checks_pending_keeps_waiting(self):
        v = view(mergeStateStatus="UNSTABLE", statusCheckRollup=[BAD, PENDING])
        checks = [{"name": "build", "bucket": "pass"}]
        self.assertEqual(self.pr(v, "--max", "10m", checks=checks), "TIMEOUT pr acme/app#7")

    def test_has_hooks_is_ready(self):
        self.assertEqual(self.pr(view(mergeStateStatus="HAS_HOOKS")), f"READY 7 {H1} approved")

    def test_optional_failure_while_blocked_does_not_fail_the_wait(self):
        v = view(mergeStateStatus="BLOCKED", reviewDecision="REVIEW_REQUIRED", statusCheckRollup=[OK, BAD])
        checks = [{"name": "build", "bucket": "pass"}]
        self.assertEqual(self.pr(v, "--max", "10m", checks=checks), "TIMEOUT pr acme/app#7")

    def test_conflict_behind_and_draft(self):
        self.assertEqual(self.pr(view(mergeStateStatus="DIRTY")), "CONFLICT 7")
        self.assertEqual(self.pr(view(mergeStateStatus="BEHIND")), "BEHIND 7")
        self.assertEqual(self.pr(view(mergeStateStatus="DRAFT"), "--max", "10m"), "TIMEOUT pr acme/app#7")

    def test_required_check_commands(self):
        v = view(mergeStateStatus="BLOCKED", statusCheckRollup=[BAD])
        rc, out, err, calls = self.run_with({"pr view": v, "pr checks": [{"name": "lint", "bucket": "fail"}]}, "pr", "acme/app", "7")
        self.assertEqual(out, "FAILED 7 lint")
        self.assertEqual(calls[1], ["gh", "pr", "checks", "7", "--repo", "acme/app", "--required", "--json", "name,bucket"])

    def test_failed_names_the_checks_and_cancelled_counts(self):
        v = view(mergeStateStatus="BLOCKED", statusCheckRollup=[OK, BAD, {"conclusion": "CANCELLED", "status": "COMPLETED", "name": "e2e"}])
        checks = [{"name": "build", "bucket": "pass"}, {"name": "lint", "bucket": "fail"}, {"name": "e2e", "bucket": "cancel"}]
        self.assertEqual(self.pr(v, checks=checks), "FAILED 7 lint,e2e")

    def test_failed_status_context_uses_context_name(self):
        v = view(mergeStateStatus="BLOCKED", statusCheckRollup=[{"state": "FAILURE", "context": "ci/legacy"}])
        self.assertEqual(self.pr(v, checks=[{"name": "ci/legacy", "bucket": "fail"}]), "FAILED 7 ci/legacy")

    def test_merged_and_closed(self):
        self.assertEqual(self.pr(view(state="MERGED", mergeCommit={"oid": "m9"})), "MERGED 7 m9")
        self.assertEqual(self.pr(view(state="CLOSED")), "CLOSED 7")

    def test_changes_requested(self):
        self.assertEqual(self.pr(view(reviewDecision="CHANGES_REQUESTED", mergeStateStatus="BLOCKED")), "CHANGES_REQUESTED 7")

    def test_head_moved_only_with_sha(self):
        self.assertEqual(self.pr(view(headRefOid=H2), "--sha", H1), f"HEAD_MOVED 7 {H2}")
        self.assertEqual(self.pr(view(headRefOid=H2)), f"READY 7 {H2} approved")
        self.assertEqual(self.pr(view(), "--sha", H1), f"READY 7 {H1} approved")

    def test_terminal_states_win_over_head_moved(self):
        self.assertEqual(self.pr(view(state="MERGED", headRefOid=H2, mergeCommit={"oid": "m9"}), "--sha", H1), "MERGED 7 m9")

    def test_keeps_waiting_then_times_out(self):
        for v in (view(statusCheckRollup=[OK, PENDING], mergeStateStatus="BLOCKED"),
                  view(statusCheckRollup=[], mergeStateStatus="UNKNOWN", reviewDecision=""),
                  view(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"),
                  view(mergeStateStatus="BLOCKED")):
            self.now, self.sleeps = 0.0, []
            self.assertEqual(self.pr(v, "--max", "20m"), "TIMEOUT pr acme/app#7")
            self.assertEqual(self.sleeps, [300.0] * 4)

    def test_merged_without_merge_commit_keeps_waiting(self):
        self.assertEqual(self.pr(view(state="MERGED"), "--max", "10m"), "TIMEOUT pr acme/app#7")

    def test_event_after_a_few_polls(self):
        views = iter([view(mergeStateStatus="BLOCKED", statusCheckRollup=[PENDING]), view(mergeStateStatus="BLOCKED", statusCheckRollup=[PENDING]), view()])
        with mock.patch.object(W, "run_cmd", side_effect=lambda a: json.dumps(next(views))):
            rc, out, _ = self.main("pr", "acme/app", "7")
        self.assertEqual((rc, out), (0, f"READY 7 {H1} approved"))
        self.assertEqual(self.sleeps, [300.0, 300.0])

    def test_gh_args(self):
        rc, out, err, calls = self.run_with({"pr view": view()}, "pr", "acme/app", "7")
        self.assertEqual(calls[0][:6], ["gh", "pr", "view", "7", "--repo", "acme/app"])
        self.assertIn("--json", calls[0])

    def test_every_override(self):
        self.run_with({"pr view": view(mergeStateStatus="BLOCKED")}, "pr", "acme/app", "7", "--every", "10s", "--max", "30s")
        self.assertEqual(self.sleeps, [10.0] * 3)

    def test_default_max_is_three_days(self):
        self.run_with({"pr view": view(mergeStateStatus="BLOCKED")}, "pr", "acme/app", "7", "--every", "1d")
        self.assertEqual(self.sleeps, [86400.0] * 3)


class ErrorTests(Base):
    def test_transient_errors_retry_then_succeed(self):
        seq = iter([subprocess.CalledProcessError(1, ["gh"], stderr="boom"), subprocess.CalledProcessError(1, ["gh"], stderr="boom"), json.dumps(view())])

        def run(args):
            out = next(seq)
            if isinstance(out, Exception):
                raise out
            return out

        with mock.patch.object(W, "run_cmd", side_effect=run):
            rc, out, _ = self.main("pr", "acme/app", "7")
        self.assertEqual((rc, out), (0, f"READY 7 {H1} approved"))

    def test_three_errors_in_a_row_exit_error_with_first_line(self):
        err = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 502: bad gateway\nsecond line")
        rc, out, _, _ = self.run_with({"pr view": err}, "pr", "acme/app", "7")
        self.assertEqual((rc, out), (0, "ERROR HTTP 502: bad gateway"))
        self.assertEqual(len(self.sleeps), 2)

    def test_error_streak_resets_after_a_good_poll(self):
        bad = subprocess.CalledProcessError(1, ["gh"], stderr="x")
        pending = json.dumps(view(mergeStateStatus="BLOCKED"))
        seq = iter([bad, bad, pending, bad, bad, json.dumps(view())])

        def run(args):
            out = next(seq)
            if isinstance(out, Exception):
                raise out
            return out

        with mock.patch.object(W, "run_cmd", side_effect=run):
            rc, out, _ = self.main("pr", "acme/app", "7")
        self.assertEqual(out, f"READY 7 {H1} approved")

    def test_bad_json_counts_as_an_error(self):
        rc, out, _, _ = self.run_with({"pr view": "not json"}, "pr", "acme/app", "7")
        self.assertTrue(out.startswith("ERROR "))


class UsageTests(Base):
    def test_usage_errors_exit_2(self):
        for argv in (["pr", "acme/app"], ["pr", "acme/app", "x"], ["nope"], [], ["dagster", "job", "1"]):
            with self.subTest(argv=argv):
                rc, out, err = self.main(*argv)
                self.assertEqual(rc, 2)
                self.assertEqual(out, "")

    def test_bad_duration_exits_2(self):
        rc, out, err = self.main("pr", "acme/app", "7", "--every", "soon")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("bad duration", err)

    def test_every_under_ten_seconds_exits_2(self):
        rc, out, err = self.main("pr", "acme/app", "7", "--every", "5s")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("10s", err)

    def test_sha_must_be_forty_hex_chars(self):
        for bad in ("abc123", "g" * 40, "a" * 39):
            rc, out, err = self.main("pr", "acme/app", "7", "--sha", bad)
            self.assertEqual((rc, out), (2, ""))
            self.assertIn("40", err)

    def test_help_runs(self):
        r = subprocess.run([sys.executable, str(BIN / "wait-for"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("wait-for", r.stdout)

    def test_file_is_executable(self):
        self.assertTrue(os.access(BIN / "wait-for", os.X_OK))


class DeployTests(Base):
    def deploy(self, table, repo, *extra):
        rc, out, err, calls = self.run_with(table, "deploy", repo, "s1", *extra)
        self.assertEqual(rc, 0, err)
        return out, calls

    def test_branch_rule(self):
        out, calls = self.deploy({"branches/prod": "h9\n", "compare": "ahead\n"}, "acme/app")
        self.assertEqual(out, "DEPLOYED s1 h9")
        self.assertEqual(calls[0], ["gh", "api", "repos/acme/app/branches/prod", "--jq", ".commit.sha"])
        self.assertEqual(calls[1], ["gh", "api", "repos/acme/app/compare/s1...h9", "--jq", ".status"])

    def test_branch_not_yet_times_out(self):
        out, _ = self.deploy({"branches/prod": "h9\n", "compare": "diverged\n"}, "acme/app", "--max", "10m")
        self.assertEqual(out, "TIMEOUT deploy acme/app s1")

    def test_workflow_failure_exits_deploy_failed(self):
        runs = [
            {"databaseId": 80, "headSha": "n1", "status": "in_progress", "conclusion": ""},
            {"databaseId": 79, "headSha": "old", "status": "completed", "conclusion": "success"},
            {"databaseId": 77, "headSha": "s1", "status": "completed", "conclusion": "failure"},
        ]
        out, calls = self.deploy({"run list": runs, "compare/s1...old": "behind", "compare/s1...s1": "identical"}, "acme/web")
        self.assertEqual(out, "DEPLOY_FAILED s1 77")
        self.assertEqual(calls[0], ["gh", "run", "list", "--repo", "acme/web", "--workflow", "deploy", "--branch", "main",
                                    "--json", "databaseId,headSha,status,conclusion", "--limit", "20"])
        self.assertEqual(len(calls), 3)

    def test_workflow_passes_over_cancelled_and_skipped_runs(self):
        runs = [
            {"databaseId": 83, "headSha": "s1", "status": "completed", "conclusion": "cancelled"},
            {"databaseId": 82, "headSha": "s1", "status": "completed", "conclusion": "skipped"},
            {"databaseId": 81, "headSha": "s1", "status": "completed", "conclusion": "success"},
        ]
        out, calls = self.deploy({"run list": runs, "compare": "identical"}, "acme/web")
        self.assertEqual(out, "DEPLOYED s1 81")
        self.assertEqual(len(calls), 2)  # passed-over runs cost no compare call
        timed_out = [dict(runs[0], conclusion="timed_out")]
        out, _ = self.deploy({"run list": timed_out, "compare": "identical"}, "acme/web")
        self.assertEqual(out, "DEPLOY_FAILED s1 83")
        out, _ = self.deploy({"run list": runs[:2]}, "acme/web", "--max", "10m")
        self.assertEqual(out, "TIMEOUT deploy acme/web s1")

    def test_workflow_newest_five_cap(self):
        old = [{"databaseId": i, "headSha": f"o{i}", "status": "completed", "conclusion": "success"} for i in range(10, 0, -1)]
        out, calls = self.deploy({"run list": old, "compare": "behind"}, "acme/web", "--max", "10m")
        self.assertEqual(out, "TIMEOUT deploy acme/web s1")
        self.assertEqual(len(calls), 3 * (1 + 5))  # three polls

    def test_release_tag(self):
        out, calls = self.deploy({"releases/latest": "v1.2\n", "compare": "behind\n"}, "acme/lib", "--max", "10m")
        self.assertEqual(out, "TIMEOUT deploy acme/lib s1")
        self.assertEqual(calls[0], ["gh", "api", "repos/acme/lib/releases/latest", "--jq", ".tag_name"])
        self.assertEqual(calls[1], ["gh", "api", "repos/acme/lib/compare/s1...v1.2", "--jq", ".status"])
        out, _ = self.deploy({"releases/latest": "v1.3\n", "compare": "ahead\n"}, "acme/lib")
        self.assertEqual(out, "DEPLOYED s1 v1.3")

    def test_repo_without_rule_exits_2(self):
        rc, out, err, calls = self.run_with({}, "deploy", "acme/other", "s1")
        self.assertEqual((rc, out, calls), (2, "", []))
        self.assertIn("acme/other", err)

    def test_default_max_is_four_hours(self):
        self.deploy({"branches/prod": "h9\n", "compare": "diverged\n"}, "acme/app", "--every", "1h")
        self.assertEqual(self.sleeps, [3600.0] * 4)


class DagsterTests(Base):
    def setUp(self):
        super().setUp()
        os.environ["DAGSTER_TOKEN"] = "t1"

    def run_gql(self, replies, *argv):
        seq = iter(replies)
        with mock.patch.object(W, "gql", side_effect=lambda *a: next(seq)) as g:
            result = self.main(*argv)
        return result + (g,)

    def test_backfill_state_terminal_rule(self):
        mk = lambda st, n, runs: {"__typename": "PartitionBackfill", "status": st, "numPartitions": n,
                                  "partitionStatuses": {"results": [{"partitionName": str(i), "runId": None, "runStatus": s} for i, s in enumerate(runs)]}}
        self.assertEqual(W.backfill_state(mk("REQUESTED", 3, ["SUCCESS", "SUCCESS"])), "RUNNING")
        self.assertEqual(W.backfill_state(mk("COMPLETED", 2, ["SUCCESS", "STARTED"])), "RUNNING")
        self.assertEqual(W.backfill_state(mk("COMPLETED", 2, ["SUCCESS", "SUCCESS"])), "SUCCESS")
        self.assertEqual(W.backfill_state(mk("COMPLETED", 2, ["SUCCESS", "FAILURE"])), "FAILURE")
        self.assertEqual(W.backfill_state(mk("CANCELED", 2, ["SUCCESS", None])), "FAILURE")
        self.assertEqual(W.backfill_state({"__typename": "PythonError", "message": "x"}), "UNKNOWN")

    def test_backfill_terminal_status_without_partition_results(self):
        mk = lambda st: {"__typename": "PartitionBackfill", "status": st, "numPartitions": 0, "partitionStatuses": {"results": []}}
        for st in ("COMPLETED", "COMPLETED_SUCCESS"):
            self.assertEqual(W.backfill_state(mk(st)), "SUCCESS")
        for st in ("COMPLETED_FAILED", "FAILED", "CANCELED", "CANCELLED"):
            self.assertEqual(W.backfill_state(mk(st)), "FAILURE")
        self.assertEqual(W.backfill_state(mk("REQUESTED")), "RUNNING")

    def test_backfill_failed_status_beats_successful_partitions(self):
        part = lambda s: {"partitionName": "p", "runId": "r", "runStatus": s}
        b = {"__typename": "PartitionBackfill", "status": "COMPLETED_FAILED", "numPartitions": 1, "partitionStatuses": {"results": [part("SUCCESS")]}}
        self.assertEqual(W.backfill_state(b), "FAILURE")
        b["status"] = "COMPLETED_SUCCESS"
        self.assertEqual(W.backfill_state(b), "SUCCESS")

    def test_run_running_then_success(self):
        run = lambda s: {"runOrError": {"__typename": "Run", "runId": "r1", "status": s}}
        rc, out, err, g = self.run_gql([run("STARTED"), run("SUCCESS")], "dagster", "run", "r1")
        self.assertEqual((rc, out), (0, "SUCCEEDED"))
        self.assertEqual(g.call_args.args, ("https://example.invalid/graphql", "t1", W.RUN_QUERY, {"id": "r1"}))
        self.assertEqual(self.sleeps, [300.0])

    def test_run_failure_and_canceled(self):
        for status in ("FAILURE", "CANCELED"):
            rc, out, err, g = self.run_gql([{"runOrError": {"__typename": "Run", "runId": "r1", "status": status}}], "dagster", "run", "r1")
            self.assertEqual(out, f"FAILED {status}")

    def test_run_not_found_ends_as_error(self):
        rc, out, err, g = self.run_gql([{"runOrError": {"__typename": "RunNotFoundError"}}] * 3, "dagster", "run", "r1")
        self.assertEqual(out, "ERROR run r1: RunNotFoundError")

    def test_backfill(self):
        payload = {"__typename": "PartitionBackfill", "id": "b1", "status": "COMPLETED", "numPartitions": 1,
                   "partitionStatuses": {"results": [{"partitionName": "p", "runId": "r", "runStatus": "SUCCESS"}]}}
        rc, out, err, g = self.run_gql([{"partitionBackfillOrError": payload}], "dagster", "backfill", "b1")
        self.assertEqual(out, "SUCCEEDED")
        self.assertEqual(g.call_args.args[2:], (W.BACKFILL_QUERY, {"id": "b1"}))

    def test_backfill_not_terminal_times_out(self):
        payload = {"__typename": "PartitionBackfill", "id": "b1", "status": "REQUESTED", "numPartitions": 2,
                   "partitionStatuses": {"results": [{"partitionName": "p", "runId": "r", "runStatus": "SUCCESS"}]}}
        rc, out, err, g = self.run_gql([{"partitionBackfillOrError": payload}] * 5, "dagster", "backfill", "b1", "--max", "10m")
        self.assertEqual(out, "TIMEOUT dagster backfill b1")

    def test_default_max_is_twelve_hours(self):
        reply = {"runOrError": {"__typename": "Run", "runId": "r1", "status": "STARTED"}}
        self.run_gql([reply] * 20, "dagster", "run", "r1", "--every", "6h")
        self.assertEqual(self.sleeps, [21600.0] * 2)

    def test_load_env_file_sets_missing_vars_only(self):
        env = self.tmp / ".env"
        env.write_text('# comment\nexport DAGSTER_TOKEN="t1"\nOTHER_X=\'q v\'\nPRESET_X=new\nnot a line\n')
        os.environ["PRESET_X"] = "old"
        os.environ.pop("OTHER_X", None)
        W.load_env_file(env)
        self.assertEqual((os.environ["DAGSTER_TOKEN"], os.environ["OTHER_X"], os.environ["PRESET_X"]), ("t1", "q v", "old"))
        W.load_env_file(self.tmp / "missing.env")  # a missing file is not an error here

    def test_token_read_from_env_file(self):
        os.environ.pop("DAGSTER_TOKEN")
        (self.tmp / ".env").write_text("DAGSTER_TOKEN=t7\n")
        reply = {"runOrError": {"__typename": "Run", "runId": "r1", "status": "SUCCESS"}}
        rc, out, err, g = self.run_gql([reply], "dagster", "run", "r1")
        self.assertEqual(out, "SUCCEEDED")
        self.assertEqual(g.call_args.args[1], "t7")

    def test_missing_token_exits_2_without_polling(self):
        os.environ.pop("DAGSTER_TOKEN")
        rc, out, err, g = self.run_gql([], "dagster", "run", "r1")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("DAGSTER_TOKEN", err)
        self.assertEqual(g.call_count, 0)

    def test_no_dagster_line_exits_2(self):
        self.cfg_path.write_text("\n".join(l for l in CFG_MD.format(tmp=self.tmp).splitlines() if "Dagster" not in l))
        rc, out, err, g = self.run_gql([], "dagster", "run", "r1")
        self.assertEqual(rc, 2)

    def test_gql_posts_with_token_header_and_raises_on_errors(self):
        class Resp:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(self.body).encode()

        with mock.patch.object(W.urllib.request, "urlopen", return_value=Resp({"data": {"x": 1}})) as uo:
            self.assertEqual(W.gql("https://example.invalid/graphql", "t1", "query{x}", {"a": 1}), {"x": 1})
        req = uo.call_args.args[0]
        self.assertEqual((req.get_method(), req.get_header("Dagster-cloud-api-token"), req.get_header("Content-type")),
                         ("POST", "t1", "application/json"))
        self.assertEqual(json.loads(req.data), {"query": "query{x}", "variables": {"a": 1}})
        self.assertEqual(uo.call_args.kwargs["timeout"], 60)
        with mock.patch.object(W.urllib.request, "urlopen", return_value=Resp({"errors": [{"message": "nope"}]})):
            with self.assertRaisesRegex(RuntimeError, "nope"):
                W.gql("https://example.invalid/graphql", "t1", "query{x}", {})

    def test_token_never_printed(self):
        os.environ["DAGSTER_TOKEN"] = "sekret-123"
        with mock.patch.object(W, "gql", side_effect=RuntimeError("401 for token sekret-123")):
            rc, out, err = self.main("dagster", "run", "r1")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("ERROR "))
        self.assertNotIn("sekret-123", out + err)


if __name__ == "__main__":
    unittest.main()
