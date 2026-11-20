"""Tests for bin/eng-stats. Run: python3 -m unittest bin/tests/test_eng_stats.py"""

import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import plistlib
import subprocess
import tempfile
import unittest
from datetime import timedelta
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


S = _load("eng_stats", BIN / "eng-stats")

NOW = "2026-01-15T18:00:00Z"  # Thursday, 10:00 in Los Angeles


def node(n, author="sam", created="2026-01-10T10:00:00Z", updated="2026-01-14T10:00:00Z", merged=None,
         reviews=(), ready=(), repo="acme/billing", author_type="User"):
    return {"number": n, "repository": {"nameWithOwner": repo}, "author": {"login": author, "__typename": author_type},
            "createdAt": created, "updatedAt": updated, "mergedAt": merged, "closedAt": merged,
            "state": "MERGED" if merged else "OPEN", "isDraft": False, "additions": 40, "deletions": 3,
            "changedFiles": 4, "timelineItems": {"nodes": [{"createdAt": r} for r in ready]},
            "reviews": {"totalCount": len(reviews), "nodes": [
                {"author": {"login": r[0], "__typename": r[3] if len(r) > 3 else "User"}, "state": r[1],
                 "submittedAt": r[2]} for r in reviews]},
            "reviewThreads": {"totalCount": 2}}


def page(nodes=(), count=None, end=None, remaining=4900):
    return {"data": {"search": {"issueCount": len(nodes) if count is None else count,
                                "pageInfo": {"hasNextPage": end is not None, "endCursor": end},
                                "nodes": list(nodes)},
                     "rateLimit": {"cost": 1, "remaining": remaining, "resetAt": "x"}}}


def row(key="acme/billing#1", author="sam", created="2026-01-05T10:00:00Z", merged=None, reviews=(), ready=None,
        bot=False, updated=None):
    return {"key": key, "repo": key.split("#")[0], "number": int(key.split("#")[1]), "author": author, "bot": bot,
            "created_at": created, "ready_at": ready, "merged_at": merged, "closed_at": merged,
            "state": "MERGED" if merged else "OPEN", "draft": False, "additions": 1, "deletions": 1,
            "changed_files": 1, "threads": 0, "reviews_total": len(reviews),
            "reviews": [{"by": r[0], "bot": r[2] if len(r) > 2 else False, "state": "APPROVED", "at": r[1]}
                        for r in reviews],
            "updated_at": updated or merged or created}


def arg(args, name):
    for i, a in enumerate(args):
        if a == "-f" and args[i + 1].startswith(name + "="):
            return args[i + 1][len(name) + 1:]
    return None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.cfg = {"tz": "America/Los_Angeles", "github_org": "acme", "stats": {"team_members": ["sam", "ana"]}}
        self.calls = []
        self.handler = lambda q, after: page()
        self.team_out = None

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, args):
        self.calls.append(args)
        if args[:3] == ["gh", "api", "user"]:
            return "sam\n"
        if args[:3] == ["gh", "api", "graphql"]:
            got = self.handler(arg(args, "q"), arg(args, "after"))
            if isinstance(got, Exception):
                raise got
            return json.dumps(got)
        if args[:2] == ["gh", "api"] and "/members" in args[2]:
            if isinstance(self.team_out, Exception) or self.team_out is None:
                raise subprocess.CalledProcessError(1, args, "", "HTTP 404")
            return self.team_out
        if args[:3] == ["gh", "auth", "status"]:
            return ""
        raise AssertionError(f"unexpected command {args}")

    def main(self, *argv):
        (self.home / "config.json").write_text(json.dumps(self.cfg))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(S, "run_cmd", side_effect=self.fake), mock.patch.object(S, "SLEEP") as self.sleep, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = S.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def cmd(self, name, *extra, now=NOW):
        return self.main(name, "--home", str(self.home), "--now", now, *extra)

    def queries(self):
        return [arg(a, "q") for a in self.calls if a[:3] == ["gh", "api", "graphql"]]

    def meta(self):
        return json.loads((self.home / "cache" / "meta.json").read_text())

    def rows(self):
        lines = (self.home / "cache" / "prs.jsonl").read_text().splitlines()
        return {r["key"]: r for r in map(json.loads, lines)}

    def stats(self):
        return json.loads((self.home / "feeds" / "stats.json").read_text())


class QueryTests(Base):
    def test_query_shape_and_repo_qualifiers(self):
        self.cfg["stats"]["repos_include"] = ["billing", "web"]
        self.cfg["stats"]["repos_skip"] = ["old"]
        self.cmd("refresh", "--since", "1d")
        q = self.queries()[0]
        self.assertTrue(q.startswith("org:acme is:pr updated:2026-01-14T18:00:00Z..2026-01-15T18:00:00Z"), q)
        self.assertIn("sort:updated-asc", q)
        self.assertIn(" repo:acme/billing repo:acme/web", q)
        self.assertIn(" -repo:acme/old", q)
        query = arg(next(a for a in self.calls if a[:3] == ["gh", "api", "graphql"]), "query")
        self.assertIn("first: 50", query)
        self.assertIn("rateLimit", query)

    def test_stats_org_wins_and_fill_in_is_ignored(self):
        self.cfg["stats"]["org"] = "globex"
        self.cmd("refresh", "--since", "1d")
        self.assertIn("org:globex", self.queries()[0])
        self.cfg["stats"]["org"] = ""
        self.cfg["github_org"] = "FILL-IN"
        code, _, err = self.cmd("refresh", "--since", "1d")
        self.assertEqual(code, 2)
        self.assertIn("set stats.org", err)


class WindowTests(Base):
    def test_seven_day_windows_oldest_first_plus_repage(self):
        self.cmd("refresh", "--since", "16d")
        spans = [q.split("updated:")[1].split(" ")[0] for q in self.queries()]
        self.assertEqual(spans, ["2025-12-30T18:00:00Z..2026-01-06T18:00:00Z",
                                 "2026-01-06T18:00:00Z..2026-01-13T18:00:00Z",
                                 "2026-01-13T18:00:00Z..2026-01-15T18:00:00Z",
                                 "2026-01-13T18:00:00Z..2026-01-15T18:00:00Z"])
        self.assertEqual(self.meta()["cursor"], NOW)

    def test_over_cap_splits_in_half(self):
        full = "2026-01-14T18:00:00Z..2026-01-15T18:00:00Z"
        self.handler = lambda q, after: page(count=1500) if full in q else page([node(len(q))])
        self.cmd("refresh", "--since", "1d")
        spans = [q.split("updated:")[1].split(" ")[0] for q in self.queries()]
        self.assertEqual(spans[:3], [full, "2026-01-14T18:00:00Z..2026-01-15T06:00:00Z",
                                     "2026-01-15T06:00:00Z..2026-01-15T18:00:00Z"])
        self.assertEqual(self.meta()["truncated"], [])

    def test_one_hour_floor_marks_truncated(self):
        self.handler = lambda q, after: page(count=1500)
        self.cmd("refresh", "--since", "2h")
        self.assertEqual(self.meta()["truncated"], [
            {"from": "2026-01-15T16:00:00Z", "to": "2026-01-15T17:00:00Z"},
            {"from": "2026-01-15T17:00:00Z", "to": "2026-01-15T18:00:00Z"}])
        self.handler = lambda q, after: page()
        self.cmd("refresh", "--since", "2h", "--full")
        self.assertEqual(self.meta()["truncated"], [])

    def test_split_never_goes_below_one_hour(self):
        self.handler = lambda q, after: page(count=1500)
        self.cmd("refresh", "--since", "3h")
        self.assertEqual(self.meta()["truncated"], [
            {"from": "2026-01-15T15:00:00Z", "to": "2026-01-15T16:30:00Z"},
            {"from": "2026-01-15T16:30:00Z", "to": "2026-01-15T18:00:00Z"}])

    def test_old_truncated_entries_are_not_counted(self):
        self.cmd("run", "--since", "1d")
        meta = self.meta()
        meta["truncated"] = [{"from": "2025-09-01T00:00:00Z", "to": "2025-09-01T01:00:00Z"},
                             {"from": "2026-01-15T10:00:00Z", "to": "2026-01-15T11:00:00Z"}]
        meta["filled_from"] = "2025-08-01T00:00:00Z"
        (self.home / "cache" / "meta.json").write_text(json.dumps(meta))
        self.cmd("report")
        self.assertEqual(self.stats()["coverage"]["truncated_windows"], 1)


class PagingTests(Base):
    def test_follows_end_cursor_and_repage_catches_moved_pr(self):
        seen = {"n": 0}

        def handler(q, after):
            seen["n"] += 1
            if after is None and seen["n"] == 1:
                return page([node(1)], count=2, end="c1")
            if after == "c1" and seen["n"] == 2:
                return page([node(2)], count=2)
            return page([node(1), node(2), node(3)])  # second pass of the newest window
        self.handler = handler
        self.cmd("refresh", "--since", "1d")
        afters = [arg(a, "after") for a in self.calls if a[:3] == ["gh", "api", "graphql"]]
        self.assertEqual(afters, [None, "c1", None])
        self.assertEqual(sorted(self.rows()), ["acme/billing#1", "acme/billing#2", "acme/billing#3"])
        self.sleep.assert_any_call(1)

    def test_retries_once_on_502_then_fails(self):
        err = subprocess.CalledProcessError(1, ["gh"], "", "HTTP 502 Bad Gateway")
        tries = []

        def handler(q, after):
            tries.append(1)
            return err if len(tries) == 1 else page()
        self.handler = handler
        code, _, _ = self.cmd("refresh", "--since", "1d")
        self.assertEqual(code, 0)
        self.sleep.assert_any_call(5)
        self.handler = lambda q, after: err
        code, _, err_text = self.cmd("refresh", "--since", "1d", "--full")
        self.assertEqual(code, 1)
        self.assertIn("502", self.meta()["last_error"])

    def test_rate_stop_keeps_cursor_and_next_run_continues(self):
        self.handler = lambda q, after: page([node(1)], remaining=500)
        code, _, err = self.cmd("refresh", "--since", "14d")
        self.assertEqual(code, 0)
        self.assertIn("points left", err)
        self.assertEqual(self.meta()["cursor"], "2026-01-08T18:00:00Z")
        self.assertEqual(len(self.queries()), 1)
        self.calls.clear()
        self.handler = lambda q, after: page()
        self.cmd("refresh")
        self.assertIn("updated:2026-01-08T17:00:00Z..2026-01-15T17:00:00Z", self.queries()[0])
        self.assertIn("acme/billing#1", self.rows())
        self.assertEqual(self.meta()["cursor"], NOW)

    def test_max_pages_stops_cleanly(self):
        code, _, err = self.cmd("refresh", "--since", "14d", "--max-pages", "1")
        self.assertEqual(code, 0)
        self.assertIn("max-pages", err)
        self.assertEqual(self.meta()["cursor"], "2026-01-08T18:00:00Z")


class CacheTests(Base):
    def test_incremental_from_cursor_minus_one_hour_and_full_rebuild(self):
        self.handler = lambda q, after: page([node(1)])
        self.cmd("refresh", "--since", "1d")
        self.calls.clear()
        self.handler = lambda q, after: page([node(2)])
        self.cmd("refresh", now="2026-01-16T18:00:00Z")
        self.assertIn("updated:2026-01-15T17:00:00Z..2026-01-16T18:00:00Z", self.queries()[0])
        self.assertEqual(sorted(self.rows()), ["acme/billing#1", "acme/billing#2"])
        self.calls.clear()
        self.cmd("refresh", "--since", "1d", "--full", now="2026-01-16T18:00:00Z")
        self.assertIn("updated:2026-01-15T18:00:00Z..", self.queries()[0])
        self.assertEqual(sorted(self.rows()), ["acme/billing#2"])

    def test_org_change_rebuilds(self):
        self.handler = lambda q, after: page([node(1)])
        self.cmd("refresh", "--since", "1d")
        self.cfg["stats"]["org"] = "globex"
        self.handler = lambda q, after: page()
        self.calls.clear()
        self.cmd("refresh", "--since", "2d")
        self.assertIn("updated:2026-01-13T18:00:00Z..", self.queries()[0])
        self.assertEqual(self.rows(), {})
        self.assertEqual(self.meta()["org"], "globex")

    def test_upsert_by_key_prune_and_no_tmp_files(self):
        self.handler = lambda q, after: page([node(1, updated="2026-01-14T10:00:00Z")])
        self.cmd("refresh", "--since", "1d")
        self.handler = lambda q, after: page([node(1, updated="2026-01-15T12:00:00Z")])
        self.cmd("refresh")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows["acme/billing#1"]["updated_at"], "2026-01-15T12:00:00Z")
        self.cfg["stats"]["keep_days"] = 1
        self.handler = lambda q, after: page()
        self.cmd("refresh", now="2026-01-17T18:00:00Z")
        self.assertEqual(self.rows(), {})
        self.assertEqual(list(self.home.rglob("*.tmp")), [])

    def test_normalize_ready_bots_and_pending(self):
        n = node(5, ready=["2026-01-12T10:00:00Z", "2026-01-11T10:00:00Z"],
                 reviews=[("ana", "APPROVED", "2026-01-12T11:00:00Z"), ("lee", "PENDING", None),
                          ("ci-bot", "COMMENTED", "2026-01-12T09:00:00Z", "Bot"),
                          ("helper", "COMMENTED", "2026-01-12T09:30:00Z")])
        r = S.normalize(n, {"helper"})
        self.assertEqual(r["ready_at"], "2026-01-11T10:00:00Z")
        self.assertEqual([x["by"] for x in r["reviews"]], ["ana", "ci-bot", "helper"])
        self.assertEqual([x["bot"] for x in r["reviews"]], [False, True, True])
        self.assertFalse(r["bot"])
        self.assertEqual(r["key"], "acme/billing#5")
        self.assertTrue(S.normalize(node(6, author="deps", author_type="Bot"), set())["bot"])
        self.assertTrue(S.normalize(node(7, author="helper"), {"helper"})["bot"])
        self.assertIsNone(S.normalize({}, set()))


class TeamTests(Base):
    def test_from_github_cached_for_a_day(self):
        self.cfg["stats"]["team_slug"] = "platform"
        self.team_out = "sam\nana\nlee\n"
        self.cmd("run", "--since", "1d")
        team = json.loads((self.home / "cache" / "team.json").read_text())
        self.assertEqual(team["members"], ["ana", "lee", "sam"])
        self.assertEqual(self.stats()["team"], {"slug": "acme/platform", "size": 3, "source": "github"})
        self.calls.clear()
        self.cmd("run", now="2026-01-15T20:00:00Z")
        self.assertFalse(any("/members" in a[2] for a in self.calls if a[:2] == ["gh", "api"]))

    def test_falls_back_to_config(self):
        self.cfg["stats"]["team_slug"] = "platform"
        self.cmd("run", "--since", "1d")
        team = self.stats()["team"]
        self.assertEqual(team["source"], "config")
        self.assertEqual(team["size"], 2)
        self.assertIn("read:org", team["note"])

    def test_no_team(self):
        self.cfg["stats"] = {}
        self.cmd("run", "--since", "1d")
        s = self.stats()
        self.assertIsNone(s["team"])
        self.assertEqual(list(s["groups"]), ["me"])


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.now = S.parse_time(NOW)
        self.tz = S.local_tz("America/Los_Angeles")
        self.conf = S.settings({"tz": "America/Los_Angeles"})
        self.clock = S.Clock(self.conf, self.tz)

    def win(self, rows, members=("sam",), days=30, groups=None):
        prs = [S.Pr(r, set()) for r in rows]
        return S.group_window(prs, set(members), self.now - timedelta(days=days), self.now, self.clock, groups or {})

    def test_median_and_p90(self):
        self.assertEqual(S.median([3, 1, 2]), 2)
        self.assertEqual(S.median([4, 1, 2, 3]), 2.5)
        self.assertEqual(S.p90(list(range(1, 11))), 9)
        self.assertEqual(S.p90(list(range(1, 12))), 10)
        self.assertEqual(S.spread([1, 2, 3, 4]), {"median": None, "p90": None})
        self.assertEqual(S.spread([1, 2, 3, 4, 5]), {"median": 3, "p90": 5})

    def test_ttfr_ignores_author_and_bots_and_clamps(self):
        rows = [row(f"acme/billing#{i}", created="2026-01-10T10:00:00Z", merged="2026-01-12T10:00:00Z",
                    reviews=[("sam", "2026-01-10T10:30:00Z"), ("ci", "2026-01-10T10:45:00Z", True),
                             ("ana", "2026-01-10T12:00:00Z")]) for i in range(4)]
        rows.append(row("acme/billing#9", created="2026-01-10T10:00:00Z", ready="2026-01-10T14:00:00Z",
                        merged="2026-01-12T10:00:00Z", reviews=[("ana", "2026-01-10T12:00:00Z")]))
        w = self.win(rows)
        self.assertEqual(w["ttfr_h"], {"median": 2.0, "p90": 2.0})
        self.assertEqual(w["ttm_h"]["median"], 48.0)
        self.assertEqual(w["ttm_h"]["p90"], 48.0)

    def test_counts(self):
        rows = [
            row("acme/billing#1", merged="2026-01-12T10:00:00Z",
                reviews=[("ana", "2026-01-06T10:00:00Z"), ("ana", "2026-01-07T10:00:00Z"), ("lee", "2026-01-08T10:00:00Z")]),
            row("acme/web#2", merged="2026-01-13T10:00:00Z"),
            row("acme/web#3", merged="2025-11-01T10:00:00Z"),  # outside 30 days
            row("acme/api#4", author="ana", reviews=[("sam", "2026-01-09T10:00:00Z"), ("sam", "2026-01-10T10:00:00Z")]),
            row("acme/api#5", author="sam", reviews=[("sam", "2026-01-09T10:00:00Z")]),  # own PR, not given
            row("acme/api#6", author="deps", bot=True, merged="2026-01-12T10:00:00Z"),
        ]
        w = self.win(rows, groups={"app": ["web"], "data": ["pipeline"]})
        self.assertEqual(w["merged"], 2)
        self.assertEqual(w["merged_no_review"], 1)
        self.assertEqual(w["re_reviews"], 1)
        self.assertEqual(w["reviews_given"], 1)
        self.assertEqual(w["reviews_received"], 1)
        self.assertEqual(w["by_repo_group"], {"app": 1, "data": 0, "other": 1})
        team = self.win(rows, members=("sam", "ana"))
        self.assertEqual(team["reviews_given"], 2)  # ana on #1, sam on #4; pairs are distinct
        self.assertEqual(team["merged"], 2)  # the bot's PR never counts

    def test_weekly_twelve_local_monday_weeks(self):
        rows = [row(f"acme/billing#{i}", created="2026-01-12T08:00:00Z", merged=f"2026-01-1{3 + i % 2}T10:00:00Z")
                for i in range(3)]
        rows += [row(f"acme/billing#{10 + i}", created="2026-01-05T08:00:00Z", merged="2026-01-06T08:00:00Z")
                 for i in range(2)]
        rows.append(row("acme/billing#20", created="2026-01-05T09:00:00Z", merged="2026-01-12T07:59:00Z"))  # Sun local
        prs = [S.Pr(r, set()) for r in rows]
        wk = S.group_weekly(prs, {"sam"}, self.now, self.tz, self.clock)
        self.assertEqual(len(wk["weeks"]), 12)
        self.assertEqual(wk["weeks"][0], "2025-10-27")
        self.assertEqual(wk["weeks"][-1], "2026-01-12")
        self.assertEqual(wk["merged"][-1], 3)
        self.assertEqual(wk["merged"][-2], 3)
        self.assertIsNotNone(wk["ttm_h"][-1])
        self.assertIsNotNone(wk["ttm_h"][-2])
        self.assertIsNone(wk["ttfr_h"][-1])
        self.assertEqual(wk["merged"][:10], [0] * 10)

    def test_business_hours_clock_over_a_weekend(self):
        conf = S.settings({"tz": "America/Los_Angeles", "stats": {"business_hours_clock": True}})
        clock = S.Clock(conf, self.tz)
        # Friday 17:00 to Monday 09:00 Los Angeles: one hour each side of the weekend
        self.assertEqual(clock.hours_between(S.parse_time("2026-01-10T01:00:00Z"),
                                             S.parse_time("2026-01-12T17:00:00Z")), 2.0)
        self.assertEqual(self.clock.hours_between(S.parse_time("2026-01-10T01:00:00Z"),
                                                  S.parse_time("2026-01-12T17:00:00Z")), 64.0)


class ReportTests(Base):
    def seed(self):
        rows = [node(i, author=a, created="2026-01-05T10:00:00Z", updated="2026-01-14T10:00:00Z",
                     merged="2026-01-12T10:00:00Z", reviews=[(r, "APPROVED", "2026-01-06T10:00:00Z")])
                for i, (a, r) in enumerate([("sam", "ana"), ("ana", "sam"), ("lee", "sam"), ("ana", "lee")])]
        rows.append(node(9, author="deps", author_type="Bot", merged="2026-01-12T10:00:00Z"))
        self.handler = lambda q, after: page(rows)
        self.cfg["stats"]["team_members"] = ["sam", "ana", "lee"]

    def test_shape_and_only_the_login(self):
        self.seed()
        code, _, _ = self.cmd("run", "--since", "30d")
        self.assertEqual(code, 0)
        s = self.stats()
        self.assertEqual(set(s), {"source", "version", "generated_at", "ok", "error", "last_ok_at", "login", "org", "team",
                                  "coverage", "groups", "excluded"})
        self.assertEqual(s["org"], "acme")
        self.assertTrue(s["ok"])
        self.assertEqual(s["last_ok_at"], NOW)
        self.assertEqual(s["coverage"], {"from": "2025-12-16", "to": "2026-01-15", "prs": 5, "truncated_windows": 0})
        self.assertEqual(s["excluded"], {"bot_prs": 1})
        self.assertEqual(set(s["groups"]), {"me", "team"})
        self.assertEqual(set(s["groups"]["me"]["windows"]), {"30", "90"})
        self.assertEqual(s["groups"]["team"]["windows"]["30"]["merged"], 4)
        self.assertEqual(s["groups"]["me"]["windows"]["30"]["reviews_given"], 2)

        found = []

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    found.append(k)
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                found.append(x)
        walk(s)
        for other in ("ana", "lee", "deps"):
            self.assertNotIn(other, found)
        self.assertLess(len((self.home / "feeds" / "stats.json").read_bytes()), 20000)

    def test_refresh_failure_keeps_data_and_last_ok(self):
        self.seed()
        self.cmd("run", "--since", "30d")
        self.handler = lambda q, after: subprocess.CalledProcessError(1, ["gh"], "", "HTTP 401 Bad credentials")
        code, _, _ = self.cmd("run", now="2026-01-16T18:00:00Z")
        self.assertEqual(code, 1)
        s = self.stats()
        self.assertFalse(s["ok"])
        self.assertIn("401", s["error"])
        self.assertEqual(s["last_ok_at"], NOW)
        self.assertEqual(s["groups"]["me"]["windows"]["30"]["merged"], 1)

    def test_no_cache(self):
        code, _, _ = self.cmd("report")
        self.assertEqual(code, 1)
        s = self.stats()
        self.assertFalse(s["ok"])
        self.assertEqual(s["error"], "no cache yet, run eng-stats refresh")
        self.assertNotIn("groups", s)


class CommandTests(Base):
    def test_lock_held_exits_zero(self):
        (self.home / "state").mkdir()
        with open(self.home / "state" / "eng-stats.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, _, err = self.cmd("run")
        self.assertEqual(code, 0)
        self.assertIn("lock", err)
        self.assertEqual(self.queries(), [])

    def test_no_org_exits_two(self):
        self.cfg.pop("github_org")
        code, _, err = self.cmd("run")
        self.assertEqual(code, 2)
        self.assertIn("set stats.org", err)

    def test_bad_since_exits_two(self):
        code, _, _ = self.cmd("refresh", "--since", "soon")
        self.assertEqual(code, 2)

    def test_schedule_launchd_and_cron(self):
        code, out, err = self.main("schedule", "--print", "launchd", "--home", str(self.home))
        self.assertEqual(code, 0)
        plist = plistlib.loads(out.encode())
        self.assertEqual(plist["Label"], "com.claude-setup.eng-stats")
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 6, "Minute": 30})
        self.assertEqual(plist["ProgramArguments"][2:], ["run", "--home", str(self.home), "--config",
                                                         str(self.home / "config.json")])
        self.assertEqual(plist["EnvironmentVariables"]["TZ"], "America/Los_Angeles")
        self.assertIn("launchctl bootstrap", err)
        code, out, _ = self.main("schedule", "--print", "cron", "--home", str(self.home))
        line = [l for l in out.splitlines() if not l.startswith("#")][0]
        self.assertTrue(line.startswith("30 6 * * * "), line)
        self.assertIn("eng-stats.log", line)

    def test_doctor_runs(self):
        with mock.patch.object(S, "WHICH", return_value="/usr/bin/gh"):
            code, out, _ = self.main("doctor", "--home", str(self.home))
        self.assertIn("GitHub login sam", out)
        self.assertIn("org acme", out)


class DefaultsTests(unittest.TestCase):
    def test_defaults_match_derive(self):
        derive = _load("derive_for_stats_test", REPO / "skills" / "project-status" / "derive.py")
        self.assertEqual(S.DEFAULTS["feeds"], derive.DEFAULTS["feeds"])
        self.assertEqual(S.DEFAULTS["tz"], derive.DEFAULTS["tz"])


if __name__ == "__main__":
    unittest.main()
