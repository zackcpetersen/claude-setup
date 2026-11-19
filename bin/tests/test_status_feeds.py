"""Tests for bin/status-feeds. Run: python3 -m unittest bin/tests/test_status_feeds.py"""

import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent
REPO = BIN.parent


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


F = _load("status_feeds", BIN / "status-feeds")

THURSDAY = "2026-01-15T18:00:00Z"  # 10:00 in Los Angeles, inside the default hours
SATURDAY = "2026-01-17T18:00:00Z"


def pr_node(n, **kw):
    node = {"number": n, "title": f"PR {n}", "url": f"https://github.com/acme/billing/pull/{n}", "isDraft": False,
            "createdAt": "2026-01-10T10:00:00Z", "updatedAt": "2026-01-14T10:00:00Z", "reviewDecision": "APPROVED",
            "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "additions": 40, "deletions": 3,
            "repository": {"nameWithOwner": "acme/billing"},
            "reviewThreads": {"nodes": [{"isResolved": True}, {"isResolved": False}]},
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]}}
    node.update(kw)
    return node


def ask_node(n, author="ana", events=None, repo="acme/web"):
    return {"number": n, "title": f"Ask {n}", "url": f"https://github.com/{repo}/pull/{n}",
            "createdAt": "2026-01-12T09:00:00Z", "additions": 120, "deletions": 30, "author": {"login": author},
            "repository": {"nameWithOwner": repo}, "timelineItems": {"nodes": events or []}}


def ev(at, login=None, team=None):
    return {"createdAt": at, "requestedReviewer": {"login": login} if login else {"combinedSlug": team}}


def gql_body(**data):
    base = {"mine": {"issueCount": 0, "nodes": []}, "asks": {"issueCount": 0, "nodes": []},
            "merged": {"issueCount": 0, "nodes": []}, "rateLimit": {"cost": 1, "remaining": 4900, "resetAt": "x"}}
    base.update(data)
    return json.dumps({"data": base})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.log = Path(self.tmp.name) / "triage.jsonl"
        self.cfg = {"tz": "America/Los_Angeles", "github_org": "acme",
                    "inbox": {"slack_triage_log": str(self.log), "review_teams": []}}
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def write_cfg(self):
        (self.home / "config.json").write_text(json.dumps(self.cfg))

    def fake(self, body, login="sam"):
        def run(args):
            self.calls.append(args)
            if args[:3] == ["gh", "api", "user"]:
                return login + "\n"
            if args[:3] == ["gh", "api", "graphql"]:
                if isinstance(body, Exception):
                    raise body
                return body
            if args[:3] == ["gh", "auth", "status"]:
                return ""
            raise AssertionError(f"unexpected command {args}")
        return run

    def main(self, *argv, body=None, login="sam"):
        self.write_cfg()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(F, "run_cmd", side_effect=self.fake(body if body is not None else gql_body(), login)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = F.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_feeds(self, *extra, body=None, now=THURSDAY, login="sam"):
        return self.main("run", "--home", str(self.home), "--now", now, *extra, body=body, login=login)

    def feed(self, name):
        return json.loads((self.home / "feeds" / f"{name}.json").read_text())

    def query(self):
        return next(a for a in self.calls if a[:3] == ["gh", "api", "graphql"])[-1]


class GithubTests(Base):
    def test_query_has_orgs_user_requests_and_team_aliases(self):
        self.cfg["inbox"]["github_orgs"] = ["acme", "globex"]
        self.cfg["inbox"]["review_teams"] = ["acme/data", "acme/web"]
        self.run_feeds("--only", "github")
        q = self.query()
        self.assertIn("org:acme", q)
        self.assertIn("org:globex", q)
        self.assertIn("user-review-requested:@me", q)
        self.assertIn("team_0: search", q)
        self.assertIn("team_1: search", q)
        self.assertIn("team-review-requested:acme/data", q)
        self.assertIn("team-review-requested:acme/web", q)
        self.assertIn("merged:>=2026-01-12", q)  # local Monday
        self.assertIn("rateLimit", q)

    def test_default_org_from_github_org_and_fill_in_ignored(self):
        self.run_feeds("--only", "github")
        self.assertIn("org:acme", self.query())
        self.calls.clear()
        self.cfg["github_org"] = "FILL-IN"
        self.run_feeds("--only", "github")
        self.assertNotIn("org:", self.query())

    def test_normalizes_response_into_feed_shape(self):
        body = gql_body(
            mine={"issueCount": 2, "nodes": [pr_node(88), pr_node(90, isDraft=True, commits={"nodes": []})]},
            asks={"issueCount": 1, "nodes": [ask_node(12, events=[ev("2026-01-13T08:00:00Z", login="sam")])]},
            merged={"issueCount": 1, "nodes": [{"number": 80, "title": "Old", "url": "https://github.com/acme/billing/pull/80",
                                                 "mergedAt": "2026-01-14T20:00:00Z",
                                                 "repository": {"nameWithOwner": "acme/billing"}}]})
        code, _, _ = self.run_feeds("--only", "github", body=body)
        self.assertEqual(code, 0)
        f = self.feed("github")
        self.assertTrue(f["ok"])
        self.assertEqual(f["source"], "github")
        self.assertEqual(f["login"], "sam")
        self.assertEqual(f["orgs"], ["acme"])
        self.assertEqual(f["last_ok_at"], "2026-01-15T18:00:00Z")
        self.assertEqual(f["rate"], {"cost": 1, "remaining": 4900})
        self.assertFalse(f["truncated"])
        pr = f["my_prs"][0]
        self.assertEqual(pr, {"repo": "acme/billing", "number": 88, "title": "PR 88",
                              "url": "https://github.com/acme/billing/pull/88", "draft": False,
                              "created_at": "2026-01-10T10:00:00Z", "updated_at": "2026-01-14T10:00:00Z",
                              "review_decision": "APPROVED", "mergeable": "MERGEABLE", "merge_state": "CLEAN",
                              "ci": "SUCCESS", "unresolved_threads": 1, "additions": 40, "deletions": 3})
        self.assertTrue(f["my_prs"][1]["draft"])
        self.assertIsNone(f["my_prs"][1]["ci"])
        rq = f["review_requests"][0]
        self.assertEqual(rq["author"], "ana")
        self.assertEqual(rq["requested_at"], "2026-01-13T08:00:00Z")
        self.assertEqual(rq["via"], "user")
        self.assertEqual(rq["additions"], 120)
        self.assertEqual(f["merged_recent"][0]["merged_at"], "2026-01-14T20:00:00Z")

    def test_truncated_when_search_has_more_than_returned(self):
        body = gql_body(mine={"issueCount": 70, "nodes": [pr_node(1)]})
        self.run_feeds("--only", "github", body=body)
        self.assertTrue(self.feed("github")["truncated"])

    def test_drops_self_authored_requests(self):
        body = gql_body(asks={"issueCount": 2, "nodes": [ask_node(1, author="sam"), ask_node(2, author="ana")]})
        self.run_feeds("--only", "github", body=body)
        self.assertEqual([r["number"] for r in self.feed("github")["review_requests"]], [2])

    def test_via_user_wins_over_team(self):
        self.cfg["inbox"]["review_teams"] = ["acme/data"]
        shared = ask_node(5, events=[ev("2026-01-13T08:00:00Z", login="sam"), ev("2026-01-12T08:00:00Z", team="acme/data")])
        team_only = ask_node(6, events=[ev("2026-01-11T08:00:00Z", team="acme/data")])
        body = gql_body(asks={"issueCount": 1, "nodes": [shared]},
                        team_0={"issueCount": 2, "nodes": [shared, team_only]})
        self.run_feeds("--only", "github", body=body)
        got = {r["number"]: r for r in self.feed("github")["review_requests"]}
        self.assertEqual(got[5]["via"], "user")
        self.assertEqual(got[6]["via"], "team:acme/data")
        self.assertEqual(got[6]["requested_at"], "2026-01-11T08:00:00Z")

    def test_requested_at_is_newest_event_for_the_login(self):
        events = [ev("2026-01-12T08:00:00Z", login="sam"), ev("2026-01-13T09:00:00Z", login="sam"),
                  ev("2026-01-14T10:00:00Z", login="lee")]
        body = gql_body(asks={"issueCount": 1, "nodes": [ask_node(7, events=events)]})
        self.run_feeds("--only", "github", body=body)
        self.assertEqual(self.feed("github")["review_requests"][0]["requested_at"], "2026-01-13T09:00:00Z")

    def test_requested_at_falls_back_to_created_at(self):
        body = gql_body(asks={"issueCount": 1, "nodes": [ask_node(8, events=[ev("2026-01-14T10:00:00Z", login="lee")])]})
        self.run_feeds("--only", "github", body=body)
        self.assertEqual(self.feed("github")["review_requests"][0]["requested_at"], "2026-01-12T09:00:00Z")

    def good_then(self, bad_body):
        body = gql_body(mine={"issueCount": 1, "nodes": [pr_node(88)]})
        self.assertEqual(self.run_feeds("--only", "github", body=body)[0], 0)
        code, _, err = self.run_feeds("--only", "github", body=bad_body, now="2026-01-15T19:00:00Z")
        return code, err, self.feed("github")

    def test_graphql_errors_keep_previous_data(self):
        bad = json.dumps({"data": None, "errors": [{"message": "Something went wrong"}]})
        code, err, f = self.good_then(bad)
        self.assertEqual(code, 1)
        self.assertFalse(f["ok"])
        self.assertIn("Something went wrong", f["error"])
        self.assertEqual(f["generated_at"], "2026-01-15T19:00:00Z")
        self.assertEqual(f["last_ok_at"], "2026-01-15T18:00:00Z")
        self.assertEqual(f["my_prs"][0]["number"], 88)
        self.assertIn("github", err)

    def test_gh_non_zero_exit_keeps_previous_data(self):
        bad = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 502: bad gateway\nmore")
        code, _, f = self.good_then(bad)
        self.assertEqual(code, 1)
        self.assertFalse(f["ok"])
        self.assertEqual(f["error"], "gh exited 1: HTTP 502: bad gateway")
        self.assertEqual(f["last_ok_at"], "2026-01-15T18:00:00Z")
        self.assertEqual(len(f["my_prs"]), 1)

    def test_unexpected_response_shape_writes_failure(self):
        code, err, f = self.good_then(json.dumps({"data": {"mine": "not a dict"}}))
        self.assertEqual(code, 1)
        self.assertFalse(f["ok"])
        self.assertIn("unexpected", f["error"])
        self.assertEqual(len(f["my_prs"]), 1)

    def test_failure_with_no_previous_file(self):
        code, _, _ = self.run_feeds("--only", "github", body=subprocess.TimeoutExpired(["gh"], 60))
        self.assertEqual(code, 1)
        f = self.feed("github")
        self.assertFalse(f["ok"])
        self.assertIsNone(f["last_ok_at"])
        self.assertNotIn("my_prs", f)


class RunTests(Base):
    def test_outside_hours_writes_nothing_and_force_overrides(self):
        code, _, _ = self.run_feeds(now=SATURDAY)
        self.assertEqual(code, 0)
        self.assertFalse((self.home / "feeds").exists())
        self.assertEqual(self.calls, [])
        code, _, _ = self.run_feeds("--force", now=SATURDAY)
        self.assertEqual(code, 0)
        self.assertTrue((self.home / "feeds" / "github.json").exists())

    def test_before_hours_on_a_weekday_is_skipped(self):
        self.assertEqual(self.run_feeds(now="2026-01-15T15:00:00Z")[0], 0)  # 07:00 local
        self.assertFalse((self.home / "feeds").exists())

    def test_run_creates_folders(self):
        self.run_feeds()
        for d in ("feeds", "state", "logs"):
            self.assertTrue((self.home / d).is_dir(), d)
        self.assertTrue((self.home / "feeds" / "slack.json").exists())

    def test_lock_held_exits_zero(self):
        (self.home / "state").mkdir()
        with open(self.home / "state" / "status-feeds.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, _, err = self.run_feeds()
        self.assertEqual(code, 0)
        self.assertIn("lock", err)
        self.assertFalse((self.home / "feeds" / "github.json").exists())

    def test_atomic_write_leaves_no_tmp(self):
        self.run_feeds()
        self.assertEqual(sorted(p.name for p in (self.home / "feeds").iterdir()), ["github.json", "slack.json"])

    def test_bad_config_exits_2(self):
        (self.home / "config.json").write_text("{nope")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(F.main(["run", "--home", str(self.home), "--now", THURSDAY]), 2)

    def test_bad_usage_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(F.main(["run", "--only", "jira"]), 2)


class SlackTests(Base):
    def lines(self, *rows):
        self.log.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")

    def slack(self, now=THURSDAY):
        code, _, _ = self.run_feeds("--only", "slack", now=now)
        self.assertEqual(code, 0)
        return self.feed("slack")

    def test_missing_log_is_ok_with_no_asks(self):
        f = self.slack()
        self.assertTrue(f["ok"])
        self.assertEqual(f["asks"], [])

    def test_last_verdict_wins_and_both_shapes(self):
        self.lines({"key": "C1:1.000001", "verdict": "not-now", "reason": "Sam asks about region 3", "at": "2026-01-15T16:00Z"},
                   {"ts": "C2:2.000002", "verdict": "not-now", "why": "Ana wants a review", "at": "2026-01-15T16:05:30Z"},
                   {"key": "C3:3.000003", "verdict": "not-now", "reason": "later cleared", "at": "2026-01-15T16:00Z"},
                   {"key": "C3:3.000003", "verdict": "now", "reason": "answered", "at": "2026-01-15T16:30Z"},
                   {"key": "C4:4.000004", "verdict": "skip", "reason": "not for the user", "at": "2026-01-15T16:00Z"})
        f = self.slack()
        self.assertEqual([a["key"] for a in f["asks"]], ["C1:1.000001", "C2:2.000002"])
        self.assertEqual(f["asks"][0], {"key": "C1:1.000001", "channel": "C1", "ts": "1.000001",
                                        "reason": "Sam asks about region 3", "at": "2026-01-15T16:00:00Z"})
        self.assertEqual(f["asks"][1]["reason"], "Ana wants a review")

    def test_handled_clears_and_is_listed_as_cleared_today(self):
        self.lines({"key": "C1:1.000001", "verdict": "not-now", "reason": "Sam asks", "at": "2026-01-14T20:00Z"},
                   {"key": "C1:1.000001", "verdict": "handled", "reason": "replied", "at": "2026-01-15T17:00Z"})
        f = self.slack()
        self.assertEqual(f["asks"], [])
        self.assertEqual(f["cleared"], [{"key": "C1:1.000001", "reason": "Sam asks", "at": "2026-01-15T17:00:00Z"}])

    def test_cleared_yesterday_is_not_listed(self):
        self.lines({"key": "C1:1.000001", "verdict": "not-now", "reason": "Sam asks", "at": "2026-01-13T20:00Z"},
                   {"key": "C1:1.000001", "verdict": "skip", "reason": "gone", "at": "2026-01-14T20:00Z"})
        self.assertEqual(self.slack()["cleared"], [])

    def test_lookback_edge(self):
        self.lines({"key": "C1:1.000001", "verdict": "not-now", "reason": "inside", "at": "2026-01-12T18:00Z"},
                   {"key": "C2:2.000002", "verdict": "not-now", "reason": "outside", "at": "2026-01-12T17:59Z"})
        self.assertEqual([a["reason"] for a in self.slack()["asks"]], ["inside"])

    def test_bad_lines_skipped_and_counted(self):
        self.lines("not json", {"key": "C1:1.000001", "verdict": "not-now", "reason": "ok", "at": "2026-01-15T16:00Z"},
                   {"verdict": "not-now"}, {"key": "C2:2.0", "verdict": "not-now", "at": "garbage"})
        f = self.slack()
        self.assertEqual(f["skipped_lines"], 3)
        self.assertEqual(len(f["asks"]), 1)


class DoctorScheduleTests(Base):
    def test_doctor_fails_when_gh_missing(self):
        with mock.patch.object(F, "WHICH", return_value=None):
            code, out, _ = self.main("doctor", "--home", str(self.home))
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^fail\s+gh is not on PATH - fix:")

    def test_doctor_ok_path(self):
        self.log.write_text("")
        with mock.patch.object(F, "WHICH", return_value="/usr/bin/gh"):
            code, out, _ = self.main("doctor", "--home", str(self.home))
        self.assertEqual(code, 0)
        self.assertIn("GitHub login sam", out)
        self.assertIn("warn  github feed missing", out)

    def test_doctor_empty_log_setting_uses_the_default_like_run(self):
        self.log.write_text("")
        self.cfg["inbox"]["slack_triage_log"] = ""
        with mock.patch.dict(F.DEFAULTS["inbox"], {"slack_triage_log": str(self.log)}), \
                mock.patch.object(F, "WHICH", return_value="/usr/bin/gh"):
            code, out, _ = self.main("doctor", "--home", str(self.home))
        self.assertIn(f"ok    Slack triage log {self.log}", out)

    def test_schedule_launchd_is_valid_plist(self):
        cfg = Path(self.tmp.name) / "my-config.json"
        cfg.write_text(json.dumps(self.cfg))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = F.main(["schedule", "--print", "launchd", "--home", str(self.home), "--config", str(cfg)])
        self.assertEqual(code, 0)
        plist = plistlib.loads(out.getvalue().encode())
        self.assertEqual(plist["Label"], "com.claude-setup.status-feeds")
        self.assertEqual(plist["StartInterval"], 900)
        self.assertTrue(plist["RunAtLoad"])
        args = plist["ProgramArguments"]
        self.assertEqual(args[2:], ["run", "--home", str(self.home), "--config", str(cfg)])
        self.assertTrue(args[1].endswith("status-feeds"))
        self.assertEqual(plist["EnvironmentVariables"]["TZ"], "America/Los_Angeles")
        self.assertIn("PATH", plist["EnvironmentVariables"])
        self.assertTrue(plist["StandardErrorPath"].startswith(str(self.home / "logs")))
        self.assertIn("launchctl bootstrap", err.getvalue())
        self.assertFalse((self.home / "logs").exists())  # printing installs nothing

    def test_schedule_cron_line(self):
        self.cfg["feeds"] = {"every_minutes": 10}
        code, out, _ = self.main("schedule", "--print", "cron", "--home", str(self.home))
        self.assertEqual(code, 0)
        line = [l for l in out.splitlines() if not l.startswith("#")][0]
        self.assertTrue(line.startswith("*/10 * * * * PATH="))
        self.assertIn(f"run --home {self.home} --config {self.home / 'config.json'}", line)

    def test_schedule_cron_quotes_paths_and_clamps_interval(self):
        spaced = Path(self.tmp.name) / "my home"
        spaced.mkdir()
        self.home = spaced
        self.cfg["feeds"] = {"every_minutes": 600}
        code, out, _ = self.main("schedule", "--print", "cron", "--home", str(spaced))
        line = [l for l in out.splitlines() if not l.startswith("#")][0]
        self.assertTrue(line.startswith("*/59 * * * * "))
        self.assertIn(f"--home '{spaced}'", line)


class DefaultsTests(unittest.TestCase):
    def test_defaults_match_derive(self):
        derive = _load("derive_for_feeds_test", REPO / "skills" / "project-status" / "derive.py")
        for section in ("inbox", "feeds"):
            self.assertEqual(F.DEFAULTS[section], derive.DEFAULTS[section], section)
        self.assertEqual(F.DEFAULTS["tz"], derive.DEFAULTS["tz"])


if __name__ == "__main__":
    unittest.main()
