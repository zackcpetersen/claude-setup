"""Tests for derive.py. Run: python3 -m unittest discover -s skills/project-status/tests"""

import importlib.machinery
import importlib.util
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
_loader = importlib.machinery.SourceFileLoader("ps_derive", str(HERE.parent / "derive.py"))
_spec = importlib.util.spec_from_loader("ps_derive", _loader)
D = importlib.util.module_from_spec(_spec)
_loader.exec_module(D)

UTC = timezone.utc
NOW = datetime(2026, 1, 14, 18, 0, tzinfo=UTC)  # a Wednesday; 12:00 in America/Chicago
CFG = {"tz": "America/Chicago"}


def pr(n, **kw):
    base = {"repo": "acme/billing", "number": n, "title": f"PR {n}", "url": f"https://github.com/acme/billing/pull/{n}",
            "draft": False, "updated_at": "2026-01-14T10:00:00Z", "review_decision": None, "mergeable": "MERGEABLE",
            "merge_state": "CLEAN", "ci": "SUCCESS", "unresolved_threads": 0}
    base.update(kw)
    return base


def gh(my_prs=(), reviews=(), merged=(), ok=True, gen="2026-01-14T17:55:00Z"):
    return {"source": "github", "generated_at": gen, "ok": ok, "error": None if ok else "boom",
            "my_prs": list(my_prs), "review_requests": list(reviews), "merged_recent": list(merged)}


def view_state(data=None, inbox=None, feeds=None, prev=None, now=NOW, cfg=None, errors=None):
    return D.build_view(data or {"projects": []}, cfg if cfg is not None else CFG, inbox, feeds or {}, prev or {}, now, errors)


def view(**kw):
    return view_state(**kw)[0]


def items(v):
    return v["inbox"]["items"]


def session(*its, meeting=None):
    return {"version": 1, "updated_at": "2026-01-14T17:00:00Z", "next_meeting": meeting, "items": list(its)}


def sitem(i, **kw):
    base = {"id": i, "origin": "session", "kind": "todo", "title": i, "since": "2026-01-14T10:00:00Z", "done_at": None}
    base.update(kw)
    return base


class Refs(unittest.TestCase):
    def test_github_pr_url(self):
        self.assertEqual(D.make_ref("https://github.com/acme/billing/pull/88/files"), "gh:acme/billing#88")

    def test_slack_url_and_key_match(self):
        a = D.make_ref("https://acme.slack.com/archives/C0TEAM01/p1768000000123456?thread_ts=1")
        b = D.make_ref("C0TEAM01:1768000000.123456")
        self.assertEqual(a, "slack:C0TEAM01:1768000000.123456")
        self.assertEqual(a, b)

    def test_other_url_drops_query_and_fragment(self):
        self.assertEqual(D.make_ref("https://example.com/doc?x=1#top"), "url:https://example.com/doc")

    def test_no_link_no_ref(self):
        self.assertEqual(D.make_ref(""), "")
        self.assertEqual(D.make_ref("ENG-142"), "")
        self.assertEqual(D.make_ref("http://insecure.example.com"), "")


class Effort(unittest.TestCase):
    def test_defaults_per_kind(self):
        self.assertEqual(D.default_effort("merge"), 2)
        self.assertEqual(D.default_effort("slack"), 5)
        self.assertEqual(D.default_effort("fix-ci"), 15)
        self.assertEqual(D.default_effort("ask"), 15)

    def test_review_by_size(self):
        self.assertEqual([D.default_effort("review", n) for n in (99, 100, 499, 500)], [15, 30, 30, 60])

    def test_config_override(self):
        self.assertEqual(D.default_effort("merge", None, {"merge": "10m"}), 10)
        v = view(feeds={"github": gh([pr(1, review_decision="APPROVED")])},
                 cfg={"tz": "America/Chicago", "inbox": {"effort_defaults": {"merge": 7}}})
        self.assertEqual(items(v)[0]["effort_min"], 7)

    def test_labels(self):
        self.assertEqual([D.effort_label(m) for m in (2, 60, 70)], ["2m", "1h", "1h 10m"])
        self.assertEqual(D.parse_effort("1h 10m"), 70)
        self.assertEqual(D.parse_effort("5m"), 5)


class Bands(unittest.TestCase):
    def band_of(self, **kw):
        v = view(inbox=session(sitem("x", **kw)))
        return items(v)[0]

    def test_due_yesterday_is_late_band_1(self):
        it = self.band_of(due="2026-01-13")
        self.assertEqual((it["band"], it["late"], it["due_today"]), (1, True, False))

    def test_due_today_band_1_not_late(self):
        it = self.band_of(due="2026-01-14")
        self.assertEqual((it["band"], it["late"], it["due_today"]), (1, False, True))

    def test_who_waits_band_2(self):
        self.assertEqual(self.band_of(who_waits="Ana", effort_min=30)["band"], 2)

    def test_review_and_slack_band_2(self):
        v = view(feeds={"github": gh(reviews=[{"url": "https://github.com/acme/web/pull/1", "title": "t", "author": "ana",
                                                 "requested_at": "2026-01-14T10:00:00Z", "additions": 1, "deletions": 1}]),
                        "slack": {"ok": True, "generated_at": "2026-01-14T17:55:00Z",
                                  "asks": [{"key": "C1:1.1", "channel": "C1", "ts": "1768400000.000100", "reason": "r", "at": "2026-01-14T10:00:00Z"}]}})
        self.assertEqual(sorted(i["kind"] for i in items(v) if i["band"] == 2), ["review", "slack"])

    def test_merge_band_3_fix_ci_band_4_ask_band_5(self):
        v = view(data={"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "Plain ask"}]}]},
                 feeds={"github": gh([pr(1, review_decision="APPROVED"), pr(2, ci="FAILURE")])})
        got = {i["kind"]: i["band"] for i in items(v)}
        self.assertEqual(got, {"merge": 3, "fix-ci": 4, "ask": 5})

    def test_approve_agent_band_3(self):
        self.assertEqual(self.band_of(kind="approve-agent", effort_min=2)["band"], 3)

    def test_order_inside_band(self):
        v = view(inbox=session(sitem("b", title="B", effort_min=15, since="2026-01-10T00:00:00Z"),
                               sitem("a", title="A", effort_min=15, since="2026-01-10T00:00:00Z"),
                               sitem("c", title="C", effort_min=15, since="2026-01-09T00:00:00Z"),
                               sitem("d", title="D", effort_min=10, since="2026-01-13T00:00:00Z")))
        self.assertEqual([i["title"] for i in items(v)], ["D", "C", "A", "B"])


class MyPrs(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(D.pr_kind(pr(1, mergeable="CONFLICTING", ci="FAILURE", review_decision="CHANGES_REQUESTED"))[0], "conflict")
        self.assertEqual(D.pr_kind(pr(1, ci="FAILURE", review_decision="CHANGES_REQUESTED"))[0], "fix-ci")
        self.assertEqual(D.pr_kind(pr(1, unresolved_threads=2, review_decision="APPROVED")), ("reply-review", "2 open threads"))
        self.assertEqual(D.pr_kind(pr(1, review_decision="APPROVED")), ("merge", "Approved and green"))

    def test_pending_checks_never_green(self):
        self.assertIsNone(D.pr_kind(pr(1, review_decision="APPROVED", ci=None)))
        self.assertIsNone(D.pr_kind(pr(1, review_decision="APPROVED", ci="PENDING")))
        self.assertEqual(D.pr_kind(pr(1, review_decision="APPROVED", ci=None), ["acme/billing"])[0], "merge")
        v = view(feeds={"github": gh([pr(1, review_decision="APPROVED", ci=None)])},
                 cfg={"tz": "America/Chicago", "inbox": {"no_ci_repos": ["acme/billing"]}})
        self.assertEqual(items(v)[0]["kind"], "merge")

    def test_unknown_never_conflict_null_never_merge(self):
        self.assertIsNone(D.pr_kind(pr(1, mergeable="UNKNOWN", merge_state="UNKNOWN")))
        self.assertIsNone(D.pr_kind(pr(1, review_decision=None)))
        self.assertEqual(D.pr_kind(pr(1, review_decision="APPROVED", mergeable="UNKNOWN", merge_state="UNKNOWN"))[1],
                         "Approved, merge check pending")
        self.assertIsNone(D.pr_kind(pr(1, review_decision="APPROVED", merge_state="BLOCKED")))

    def test_drafts_skipped(self):
        self.assertIsNone(D.pr_kind(pr(1, draft=True, mergeable="CONFLICTING")))


class Dedupe(unittest.TestCase):
    def test_session_and_github_merge(self):
        link = "https://github.com/acme/billing/pull/5"
        v = view(inbox=session(sitem("x", kind="ask", title="Session words", link=link, since="2026-01-10T00:00:00Z")),
                 feeds={"github": gh([pr(5, review_decision="APPROVED", updated_at="2026-01-14T10:00:00Z")])})
        self.assertEqual(len(items(v)), 1)
        it = items(v)[0]
        self.assertEqual((it["title"], it["kind"], it["id"]), ("Session words", "merge", "gh:acme/billing#5"))
        self.assertEqual(it["since"], "2026-01-10T00:00:00Z")

    def test_session_ref_given_as_url_merges_with_feed(self):
        v = view(inbox=session(sitem("x", kind="ask", title="Mine", ref="https://github.com/acme/billing/pull/5")),
                 feeds={"github": gh([pr(5, review_decision="APPROVED")])})
        self.assertEqual([(i["id"], i["title"]) for i in items(v)], [("gh:acme/billing#5", "Mine")])

    def test_merged_needs_me_ask_keeps_its_marker_and_sources(self):
        link = "https://github.com/acme/billing/pull/5"
        v = view(data={"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "Merge it", "link": link}]}]},
                 feeds={"github": gh([pr(5, ci="FAILURE")])})
        it = items(v)[0]
        self.assertEqual((it["source"], it["sources"], it.get("from_needs_me")), ("github", ["projects", "github"], True))
        plain = items(view(feeds={"github": gh([pr(6, ci="FAILURE")])}))[0]
        self.assertEqual((plain["sources"], plain.get("from_needs_me")), (["github"], None))

    def test_same_ticket_without_links_stays_two(self):
        v = view(data={"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "One", "ticket": "ENG-1"},
                                                                          {"ask": "Two", "ticket": "ENG-1"}]}]})
        self.assertEqual(len(items(v)), 2)
        self.assertEqual(len({i["id"] for i in items(v)}), 2)


class SnoozeStale(unittest.TestCase):
    def test_snooze_hides_until_date(self):
        v = view(inbox=session(sitem("x", snooze_until="2026-01-15")))
        self.assertEqual((len(items(v)), len(v["inbox"]["snoozed"]), v["inbox"]["open"]), (0, 1, 0))
        v = view(inbox=session(sitem("x", snooze_until="2026-01-14")))
        self.assertEqual(len(items(v)), 1)

    def test_stale_only_without_due(self):
        v = view(inbox=session(sitem("old", since="2026-01-01T00:00:00Z"), sitem("due", since="2026-01-01T00:00:00Z", due="2026-01-30"),
                               sitem("new", since="2026-01-12T00:00:00Z")))
        st = {i["id"]: i["stale"] for i in items(v)}
        self.assertEqual(st, {"s:old": True, "s:due": False, "s:new": False})


class SlackItems(unittest.TestCase):
    def test_title_link_ref(self):
        feed = {"ok": True, "generated_at": "2026-01-14T17:55:00Z",
                "asks": [{"key": "C1:1768400000.000100", "channel": "C1", "ts": "1768400000.000100", "reason": "x " * 80, "at": "2026-01-14T10:00:00Z"}]}
        v = view(feeds={"slack": feed}, cfg={"tz": "America/Chicago", "inbox": {"slack_url": "https://acme.slack.com/archives/"}})
        it = items(v)[0]
        self.assertEqual(it["ref"], "slack:C1:1768400000.000100")
        self.assertEqual(it["link"], "https://acme.slack.com/archives/C1/p1768400000000100")
        self.assertLessEqual(len(it["title"]), len("Reply: ") + 93)
        v = view(feeds={"slack": feed})
        self.assertEqual(items(v)[0]["link"], "")
        v = view(feeds={"slack": feed}, cfg={"tz": "America/Chicago", "inbox": {"slack_url": "https://acme.slack.com/archives"}})
        self.assertEqual(items(v)[0]["link"], "https://acme.slack.com/archives/C1/p1768400000000100")


class DoneToday(unittest.TestCase):
    def prev(self, date_="2026-01-14", ok=True, **open_):
        return {"date": date_, "open": open_ or {"gh:acme/billing#9": {"title": "Merge: x", "ref": "gh:acme/billing#9", "source": "github",
                                                                       "snoozed": False}},
                "cleared": [], "sources_ok": {"github": ok}}

    def test_inbox_done_today_counts_yesterday_not(self):
        v = view(inbox=session(sitem("a", done_at="2026-01-14T16:00:00Z"), sitem("b", done_at="2026-01-13T16:00:00Z")))
        self.assertEqual([d["title"] for d in v["inbox"]["done_today"]], ["a"])

    def review_prev(self, **kw):
        p = {"title": "Review: x", "ref": "gh:acme/billing#9", "source": "github", "kind": "review", "snoozed": False}
        p.update(kw)
        return self.prev(**{"gh:acme/billing#9": p})

    def test_gone_github_item_counts_when_ok_both_times(self):
        v, st = view_state(feeds={"github": gh()}, prev=self.review_prev())
        self.assertEqual(v["strip"]["done_today"], 1)
        self.assertEqual(st["cleared"][0]["id"], "gh:acme/billing#9")

    def test_my_pr_gone_without_merge_not_counted(self):
        # CI went back to pending after a push, or the PR became a draft: the item leaves, nothing was done.
        p = self.review_prev(kind="fix-ci", title="Fix CI: x")
        self.assertEqual(view(feeds={"github": gh([pr(9, ci="PENDING")])}, prev=p)["strip"]["done_today"], 0)
        merged = [{"title": "x", "url": "https://github.com/acme/billing/pull/9", "merged_at": "2026-01-14T17:00:00Z"}]
        v, st = view_state(feeds={"github": gh(merged=merged)}, prev=p)
        self.assertEqual((v["strip"]["done_today"], st["cleared"][0]["id"]), (1, "gh:acme/billing#9"))

    def test_truncated_feed_counts_nothing_by_absence(self):
        feed = dict(gh(), truncated=True)
        self.assertEqual(view(feeds={"github": feed}, prev=self.review_prev())["strip"]["done_today"], 0)

    def test_state_records_kind(self):
        _, st = view_state(feeds={"github": gh([pr(3, ci="FAILURE")])})
        self.assertEqual(st["open"]["gh:acme/billing#3"]["kind"], "fix-ci")

    def test_not_counted_when_github_failing_now_or_before(self):
        self.assertEqual(view(feeds={"github": gh(ok=False)}, prev=self.prev())["strip"]["done_today"], 0)
        self.assertEqual(view(feeds={"github": gh()}, prev=self.prev(ok=False))["strip"]["done_today"], 0)

    def test_not_counted_from_earlier_date_or_snoozed(self):
        self.assertEqual(view(feeds={"github": gh()}, prev=self.prev(date_="2026-01-13"))["strip"]["done_today"], 0)
        p = self.prev(**{"gh:acme/billing#9": {"title": "x", "ref": "gh:acme/billing#9", "source": "github", "snoozed": True}})
        self.assertEqual(view(feeds={"github": gh()}, prev=p)["strip"]["done_today"], 0)

    def test_projects_ask_with_pr_link_not_counted_by_absence(self):
        p = self.prev(**{"gh:acme/billing#9": {"title": "x", "ref": "gh:acme/billing#9", "source": "projects", "snoozed": False}})
        self.assertEqual(view(feeds={"github": gh()}, prev=p)["strip"]["done_today"], 0)

    def test_merged_today_counts_once_even_when_also_cleared(self):
        merged = [{"title": "x", "url": "https://github.com/acme/billing/pull/9", "merged_at": "2026-01-14T17:00:00Z"},
                  {"title": "y", "url": "https://github.com/acme/billing/pull/7", "merged_at": "2026-01-13T17:00:00Z"}]
        v, _ = view_state(feeds={"github": gh(merged=merged)}, prev=self.prev())
        self.assertEqual(v["strip"]["done_today"], 1)

    def test_reworded_projects_ask_not_counted(self):
        data = {"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "New words"}]}]}
        prev = self.prev(**{"proj:p:" + D.sha("Old words"): {"title": "Old words", "ref": "", "snoozed": False}})
        self.assertEqual(view(data=data, feeds={"github": gh()}, prev=prev)["strip"]["done_today"], 0)

    def test_slack_aged_out_not_counted_cleared_today_counts(self):
        feed = {"ok": True, "generated_at": "2026-01-14T17:55:00Z", "asks": [],
                "cleared": [{"key": "C1:1768400000.000100", "reason": "r", "at": "2026-01-14T15:00:00Z"},
                            {"key": "C1:1768300000.000100", "reason": "r", "at": "2026-01-13T15:00:00Z"}]}
        self.assertEqual(view(feeds={"slack": feed})["strip"]["done_today"], 1)

    def test_item_that_became_snoozed_not_counted(self):
        link = "https://github.com/acme/billing/pull/9"
        v, _ = view_state(inbox=session(sitem("x", link=link, snooze_until="2026-01-20")), feeds={"github": gh()}, prev=self.prev())
        self.assertEqual(v["strip"]["done_today"], 0)


class StableIds(unittest.TestCase):
    def test_pr_keeps_id_and_since_across_kinds(self):
        v1, st = view_state(feeds={"github": gh([pr(3, ci="FAILURE", created_at="2026-01-12T10:00:00Z")])})
        self.assertEqual(items(v1)[0]["id"], "gh:acme/billing#3")
        self.assertEqual(items(v1)[0]["since"], "2026-01-12T10:00:00Z")
        later = datetime(2026, 1, 14, 20, 0, tzinfo=UTC)
        v2, _ = view_state(feeds={"github": gh([pr(3, review_decision="APPROVED", created_at="2026-01-12T10:00:00Z",
                                                  updated_at="2026-01-14T19:00:00Z")])}, prev=st, now=later)
        self.assertEqual((items(v2)[0]["id"], items(v2)[0]["kind"]), ("gh:acme/billing#3", "merge"))
        self.assertEqual(items(v2)[0]["since"], items(v1)[0]["since"])

    def test_pr_since_is_first_seen_not_updated_at(self):
        prev = {"date": "2026-01-14", "open": {"gh:acme/billing#3": {"first_seen": "2026-01-02T09:00:00Z"}}}
        v = view(feeds={"github": gh([pr(3, ci="FAILURE", created_at="2026-01-10T10:00:00Z",
                                          updated_at="2026-01-14T17:00:00Z")])}, prev=prev)
        it = items(v)[0]
        self.assertEqual((it["since"], it["stale"], it["age"]), ("2026-01-02T09:00:00Z", True, "12d"))


class TimeAndFreshness(unittest.TestCase):
    def test_today_uses_tz(self):
        v, _ = view_state(now=datetime(2026, 1, 20, 2, 0, tzinfo=UTC), cfg={"tz": "America/Los_Angeles"})
        self.assertEqual(v["today"], "2026-01-19")

    def test_freshness_counts_only_in_hours(self):
        tz = D.local_tz("America/Chicago")
        cfg = D.settings({"tz": "America/Chicago"})
        feed = {"ok": True, "generated_at": "2026-01-16T23:50:00Z"}  # Friday 17:50 local
        mon_0810 = datetime(2026, 1, 19, 14, 10, tzinfo=UTC)
        mon_0835 = datetime(2026, 1, 19, 14, 35, tzinfo=UTC)
        self.assertEqual(D.source_state("github", feed, None, cfg, mon_0810, tz)["state"], "ok")
        self.assertEqual(D.source_state("github", feed, None, cfg, mon_0835, tz)["state"], "stale")

    def test_failing_and_missing(self):
        tz = D.local_tz("America/Chicago")
        cfg = D.settings({})
        self.assertEqual(D.source_state("github", {"ok": False, "error": "auth"}, None, cfg, NOW, tz)["state"], "failing")
        self.assertEqual(D.source_state("github", None, None, cfg, NOW, tz)["state"], "missing")
        self.assertEqual(D.source_state("session", None, "bad json", cfg, NOW, tz)["state"], "failing")

    def test_cap_does_not_drop_items(self):
        its = [sitem(f"t{n}") for n in range(12)]
        v, _ = view_state(inbox=session(*its), cfg={"tz": "America/Chicago", "inbox": {"cap": 3, "home_count": 1}})
        self.assertEqual(len(items(v)), 12)
        self.assertEqual(v["inbox_config"], {"cap": 3, "home_count": 1})

    def test_next_meeting_only_later_today(self):
        later = {"title": "Planning", "at": "2026-01-14T21:00:00Z"}
        self.assertEqual(view(inbox=session(meeting=later))["strip"]["next_meeting"]["time"], "15:00")
        for at in ("2026-01-14T17:00:00Z", "2026-01-15T16:00:00Z"):
            self.assertIsNone(view(inbox=session(meeting={"title": "x", "at": at}))["strip"]["next_meeting"])


class ProjectItems(unittest.TestCase):
    def test_nudges_and_oneoffs(self):
        data = {"projects": [], "waiting_on": [{"person": "Ana", "what": "Results", "project_id": "p", "nudge_due": "2026-01-14"},
                                               {"person": "Lee", "what": "Later", "project_id": "p", "nudge_due": "2026-01-15"}],
                "one_offs": [{"title": "Cert", "needs_me": True, "state": "not started"}, {"title": "Done one", "needs_me": True, "state": "done"},
                             {"title": "Not mine", "state": "not started"}]}
        got = sorted(i["id"] for i in items(view(data=data)))
        self.assertEqual(got, ["nudge:p:Ana:" + D.sha("Results", 8), "oneoff:" + D.sha("Cert")])

    def test_same_person_nudges_and_same_title_oneoffs_get_distinct_ids(self):
        data = {"projects": [], "waiting_on": [{"person": "Ana", "what": "Results", "project_id": "p", "nudge_due": "2026-01-14"},
                                               {"person": "Ana", "what": "Contract", "project_id": "p", "nudge_due": "2026-01-14"}],
                "one_offs": [{"title": "Cert", "needs_me": True}, {"title": "Cert", "needs_me": True}]}
        ids = [i["id"] for i in items(view(data=data))]
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4)

    def test_hid_is_8_hex(self):
        it = items(view(inbox=session(sitem("x"))))[0]
        self.assertRegex(it["hid"], r"^[0-9a-f]{8}$")
        self.assertEqual(it["hid"], D.hid_of("s:x"))



TODAY = date(2026, 1, 14)
CHI = D.local_tz("America/Chicago")
LA = D.local_tz("America/Los_Angeles")


def job(**kw):
    base = {"label": "Backfill", "done": 610000, "total": 1000000, "unit": "files", "per_day": 45000,
            "updated": "2026-01-14T15:00:00Z"}
    base.update(kw)
    return base


def jv(j, today=TODAY):
    return D.job_views({"jobs": [j]}, today, CHI)[0]


class Jobs(unittest.TestCase):
    def test_eta_computed_from_updated_day(self):
        got = jv(job(updated="2026-01-12T15:00:00Z"))
        self.assertEqual((got["eta"], got["eta_source"], got["pct"]), ("2026-01-21", "computed", 61))  # 01-12 + ceil(8.67)

    def test_job_that_stopped_reporting_goes_late(self):
        got = jv(job(done=865000, updated="2026-01-04T15:00:00Z"))  # 3 days left, last report 10 days ago
        self.assertEqual(got["eta"], "2026-01-07")
        self.assertTrue(got["late"])
        self.assertTrue(got["stale"])

    def test_given_eta_wins(self):
        got = jv(job(eta="2026-02-01"))
        self.assertEqual((got["eta"], got["eta_source"]), ("2026-02-01", "given"))

    def test_no_per_day_no_eta(self):
        self.assertIsNone(jv(job(per_day=None))["eta"])

    def test_stale_after_two_days(self):
        self.assertFalse(jv(job(updated="2026-01-12T15:00:00Z"))["stale"])
        self.assertTrue(jv(job(updated="2026-01-11T15:00:00Z"))["stale"])

    def test_finished(self):
        got = jv(job(done=1000000, eta="2026-01-01"))
        self.assertTrue(got["finished"])
        self.assertFalse(got["late"])
        self.assertEqual(got["pct"], 100)

    def test_pct_clamps_and_null_on_zero_total(self):
        self.assertEqual(jv(job(done=2000000))["pct"], 100)
        self.assertEqual(jv(job(done=-5))["pct"], 0)
        self.assertIsNone(jv(job(total=0))["pct"])
        self.assertIsNone(jv(job(total=None))["pct"])

    def test_left_text(self):
        self.assertEqual(jv(job())["left"], "390,000 files")
        self.assertEqual(jv(job(unit=""))["left"], "390,000")


def proj(pid, **kw):
    base = {"id": pid, "name": pid.title()}
    base.update(kw)
    return base


class Timeline(unittest.TestCase):
    def test_window_and_kinds(self):
        p = proj("a", deadline="2026-01-30", next_milestone="Cutover", next_milestone_date="2026-01-20",
                 needs_me=[{"ask": "Sign it", "due": "2026-01-16", "link": "https://example.com/x"}])
        jobs = {"a": [{"label": "Backfill", "eta": "2026-01-22", "finished": False}]}
        tl = D.timeline_view([p], jobs, TODAY)
        self.assertEqual((tl["from"], tl["to"], tl["days"]), ("2026-01-14", "2026-02-03", 21))
        self.assertEqual([(e["kind"], e["day"]) for e in tl["events"]],
                         [("ask", 2), ("milestone", 6), ("job", 8), ("deadline", 16)])
        self.assertEqual(tl["events"][2]["label"], "Backfill done")
        self.assertEqual(tl["events"][0]["link"], "https://example.com/x")
        self.assertEqual(tl["events"][3]["sub"], "A")

    def test_after_window_dropped(self):
        self.assertEqual(D.timeline_view([proj("a", deadline="2026-02-04")], {}, TODAY)["events"], [])
        self.assertEqual(len(D.timeline_view([proj("a", deadline="2026-02-03")], {}, TODAY)["events"]), 1)

    def test_passed_dates_kept_late_at_day_0(self):
        p = proj("a", deadline="2026-01-10", needs_me=[{"ask": "x", "due": "2026-01-12"}])
        jobs = {"a": [{"label": "J", "eta": "2026-01-07", "finished": False}, {"label": "F", "eta": "2026-01-07", "finished": True}]}
        ev = D.timeline_view([p], jobs, TODAY)["events"]
        self.assertEqual(len(ev), 3)
        self.assertTrue(all(e["late"] and e["day"] == 0 and not e["soon"] for e in ev))

    def test_soon(self):
        ev = D.timeline_view([proj("a", deadline="2026-01-14"), proj("b", deadline="2026-01-17"),
                              proj("c", deadline="2026-01-18")], {}, TODAY)["events"]
        self.assertEqual([e["soon"] for e in ev], [True, True, False])

    def test_sort_by_day_then_priority_then_name(self):
        ps = [proj("zed", deadline="2026-01-20", priority="P1"), proj("abe", deadline="2026-01-20", priority="P2"),
              proj("bob", deadline="2026-01-20"), proj("early", deadline="2026-01-15", priority="P4")]
        self.assertEqual([e["project_id"] for e in D.timeline_view(ps, {}, TODAY)["events"]], ["early", "zed", "abe", "bob"])

    def test_cap_and_more(self):
        ps = [proj(f"p{i:02d}", deadline="2026-01-20") for i in range(15)]
        tl = D.timeline_view(ps, {}, TODAY)
        self.assertEqual((len(tl["events"]), tl["more"]), (12, 3))

    def test_project_filter(self):
        ps = [proj("a", deadline="2026-01-20"), proj("b", deadline="2026-01-21")]
        self.assertEqual([e["project_id"] for e in D.timeline_view(ps, {}, TODAY, "b")["events"]], ["b"])


class Pipeline(unittest.TestCase):
    def test_none_without_feed(self):
        self.assertIsNone(D.pipeline_view(None))

    def test_stages_and_pills(self):
        feed = gh(my_prs=[pr(3, draft=True, created_at="2026-01-03"), pr(2, review_decision="APPROVED", created_at="2026-01-02"),
                          pr(5, ci="FAILURE", created_at="2026-01-05"), pr(4, mergeable="CONFLICTING", created_at="2026-01-01"),
                          pr(6, mergeable="UNKNOWN", ci=None, created_at="2026-01-06")],
                  reviews=[{"url": "u1"}, {"url": "u2"}],
                  merged=[{"repo": "acme/web", "number": 9, "url": "m9", "merged_at": "2026-01-12T10:00:00Z"},
                          {"repo": "acme/web", "number": 10, "url": "m10", "merged_at": "2026-01-13T10:00:00Z"}])
        pv = D.pipeline_view(feed)
        st = {s["key"]: s for s in pv["stages"]}
        self.assertEqual([s["key"] for s in pv["stages"]], ["draft", "review", "approved", "merged"])
        self.assertEqual([p["label"] for p in st["review"]["pills"]], ["billing#4", "billing#5", "billing#6"])
        self.assertEqual([(p["ci_failed"], p["conflict"]) for p in st["review"]["pills"]],
                         [(False, True), (True, False), (False, False)])
        self.assertEqual((st["draft"]["n"], st["approved"]["n"]), (1, 1))
        self.assertEqual([p["label"] for p in st["merged"]["pills"]], ["web#10", "web#9"])
        self.assertEqual(st["merged"]["label"], "Merged this week")
        self.assertEqual(pv["reviews_owed"], 2)
        self.assertFalse(pv["stale"])

    def test_failing_feed_marks_stale(self):
        v = view(feeds={"github": {"ok": False, "my_prs": [pr(1)]}})
        self.assertTrue(v["pipeline"]["stale"])


class Waiting(unittest.TestCase):
    def test_days_nudge_and_flags(self):
        rows = [{"since": "2026-01-05", "nudge_due": "2026-01-12"}, {"since": "2026-01-10", "nudge_due": "2026-01-14"},
                {"nudge_due": "2026-01-20"}]
        wv = D.waiting_view(rows, TODAY, CHI)
        self.assertEqual([(r["days"], r["nudge_at"], r["late"], r["due_today"]) for r in wv["rows"]],
                         [(9, 7, True, False), (4, 4, False, True), (None, None, False, False)])
        self.assertEqual(wv["scale_days"], 14)

    def test_scale_grows(self):
        wv = D.waiting_view([{"since": "2025-12-20", "nudge_due": "2026-01-30"}], TODAY, CHI)
        self.assertEqual(wv["scale_days"], 41)

    def test_local_date_of_since(self):
        wv = D.waiting_view([{"since": "2026-11-19T06:30:00Z"}], date(2026, 11, 20), LA)
        self.assertEqual(wv["rows"][0]["days"], 2)  # 11-18 local


class Delivered(unittest.TestCase):
    def test_only_confirm_with_due_and_snoozed_included(self):
        its = [{"kind": "confirm", "hid": "a", "title": "A", "since": "2026-01-08T18:00:00Z", "due": "2026-01-16"},
               {"kind": "confirm", "hid": "b", "title": "B", "since": "2026-01-01T18:00:00Z"},
               {"kind": "todo", "hid": "c", "title": "C", "since": "2026-01-01T18:00:00Z", "due": "2026-01-15"}]
        snz = [{"kind": "confirm", "hid": "d", "title": "D", "since": "2026-01-01T18:00:00Z", "due": "2026-01-10"}]
        got = D.delivered_view(its, snz, TODAY, CHI)
        self.assertEqual([g["hid"] for g in got], ["d", "a"])
        d, a = got
        self.assertEqual((a["total"], a["elapsed"], a["left"], a["late"]), (8, 6, 2, False))
        self.assertEqual((d["total"], d["elapsed"], d["left"], d["late"]), (9, 9, -4, True))

    def test_local_since_near_midnight(self):
        its = [{"kind": "confirm", "hid": "a", "title": "A", "since": "2026-11-19T06:30:00Z", "due": "2026-11-21"}]
        got = D.delivered_view(its, [], date(2026, 11, 20), LA)[0]
        self.assertEqual((got["since"], got["total"], got["elapsed"]), ("2026-11-18", 3, 2))


class StatsSource(unittest.TestCase):
    def setUp(self):
        self.cfg = D.settings({})

    def st(self, feed, err=None, now=NOW):
        return D.source_state("stats", feed, err, self.cfg, now, CHI)

    def test_ok_stale_failing_missing(self):
        self.assertEqual(self.st({"ok": True, "generated_at": "2026-01-13T13:00:00Z"})["state"], "ok")
        self.assertEqual(self.st({"ok": True, "generated_at": "2026-01-13T11:00:00Z"})["state"], "stale")
        self.assertEqual(self.st({"ok": False, "error": "x", "generated_at": "2026-01-14T11:00:00Z"})["state"], "failing")
        self.assertEqual(self.st(None)["state"], "missing")

    def test_stats_source_listed_only_with_file(self):
        self.assertNotIn("stats", [s["name"] for s in view()["sources"]])
        v = view(feeds={"stats": {"ok": True, "generated_at": "2026-01-14T11:00:00Z", "groups": {}}})
        self.assertEqual(v["sources"][-1]["name"], "stats")
        self.assertEqual(v["stats"]["groups"], {})
        self.assertEqual(view(errors={"stats": "bad"})["sources"][-1]["state"], "failing")
        self.assertIsNone(view()["stats"])

    def test_as_of_has_date_when_not_today(self):
        self.assertEqual(self.st({"ok": True, "generated_at": "2026-01-14T17:00:00Z"})["as_of"], "11:00")
        self.assertEqual(self.st({"ok": True, "generated_at": "2026-01-13T17:00:00Z"})["as_of"], "01-13 11:00")


LCFG = D.settings({"tracker_url": "https://tracker.example.com/browse/", "github_org": "acme",
                   "inbox": {"slack_url": "https://acme.slack.com/archives/"},
                   "links": {"patterns": [{"match": r"run-(\d+)", "url": "https://runs.example.com/{1}"}],
                             "repos": ["billing"]}})


class Links(unittest.TestCase):
    def test_ticket_key_segment(self):
        self.assertEqual(D.link_mentions("Ship ENG-142 today", LCFG),
                         [{"text": "Ship "}, {"text": "ENG-142", "url": "https://tracker.example.com/browse/ENG-142"},
                          {"text": " today"}])

    def test_repo_ref_slack_key_pattern_and_url(self):
        segs = D.link_mentions("See billing #91, C0TEAM01:1768000000.123456, run-77 and https://example.com/a.", LCFG)
        urls = [s["url"] for s in segs if "url" in s]
        self.assertEqual(urls, ["https://github.com/acme/billing/pull/91",
                                "https://acme.slack.com/archives/C0TEAM01/p1768000000123456",
                                "https://runs.example.com/77", "https://example.com/a"])
        self.assertEqual("".join(s["text"] for s in segs),
                         "See billing #91, C0TEAM01:1768000000.123456, run-77 and https://example.com/a.")

    def test_ask_gets_parts_with_tracker(self):
        data = {"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "Approve ENG-142"}]}]}
        v = view(data=data, cfg={"tz": "America/Chicago", "tracker_url": "https://tracker.example.com/browse/"})
        parts = v["projects"][0]["needs_me"][0]["ask_parts"]
        self.assertEqual(parts[1], {"text": "ENG-142", "url": "https://tracker.example.com/browse/ENG-142"})
        self.assertEqual(v["unlinked"], [])
        self.assertNotIn("ask_parts", data["projects"][0]["needs_me"][0])  # input not changed

    def test_ask_without_tracker_is_unlinked(self):
        data = {"projects": [{"id": "p", "name": "P", "needs_me": [{"ask": "Approve ENG-142"}]}]}
        v = view(data=data)
        self.assertEqual(v["unlinked"], [{"where": "projects.p.needs_me[0].ask", "text": "ENG-142", "why": "no tracker_url"}])
        self.assertNotIn("ask_parts", v["projects"][0]["needs_me"][0])

    def test_standards_are_not_tickets(self):
        segs = D.link_mentions("Use UTF-8 and SHA-256 for ENG-142", LCFG)
        self.assertEqual([s["text"] for s in segs if "url" in s], ["ENG-142"])

    def test_ticket_keys_limit_prefixes(self):
        cfg = D.settings({"tracker_url": "https://tracker.example.com/browse/", "links": {"ticket_keys": ["eng"]}})
        segs = D.link_mentions("ENG-142 and OPS-7", cfg)
        self.assertEqual([s["text"] for s in segs if "url" in s], ["ENG-142"])

    def test_unknown_word_hash_number_is_plain(self):
        segs = D.link_mentions("Ran chunk #2 of billing #91", LCFG)
        self.assertEqual([s["text"] for s in segs if "url" in s], ["billing #91"])

    def test_feed_repos_are_known(self):
        data = {"projects": [{"id": "p", "name": "P", "summary": "Waiting on ledger #5, step #3"}]}
        feeds = {"github": {"ok": True, "my_prs": [{"repo": "acme/ledger", "number": 5}]}}
        v = view(data=data, cfg={"tz": "America/Chicago", "github_org": "acme"}, feeds=feeds)
        parts = v["projects"][0]["summary_parts"]
        self.assertEqual([s["url"] for s in parts if "url" in s], ["https://github.com/acme/ledger/pull/5"])

    def test_pattern_with_optional_group_does_not_crash(self):
        cfg = D.settings({"links": {"patterns": [{"match": r"run(/(\d+))?", "url": "https://runs.example.com{1}"}]}})
        segs = D.link_mentions("run and run/4", cfg)
        self.assertEqual([s["url"] for s in segs if "url" in s], ["https://runs.example.com/4"])

    def test_javascript_url_never_a_link(self):
        cfg = D.settings({"links": {"patterns": [{"match": r"bad-(\d+)", "url": "javascript:alert({1})"}]}})
        self.assertFalse(any("url" in s for s in D.link_mentions("bad-1 javascript:alert(1)", cfg)))

    def test_thread_word_without_link_listed(self):
        data = {"projects": [], "waiting_on": [{"person": "Ana", "what": "Answer in the Slack thread", "since": "2026-01-10"},
                                               {"person": "Lee", "what": "Answer in the Slack thread too", "link": "https://example.com/t"}]}
        un = view(data=data)["unlinked"]
        self.assertEqual([(u["where"], u["why"]) for u in un], [("waiting_on[0].what", "names a thread or page but has no link")])

    def test_no_mentions_no_entries(self):
        data = {"projects": [{"id": "p", "name": "Plain", "summary": "Nothing to link here."}]}
        self.assertEqual(view(data=data)["unlinked"], [])
        self.assertEqual(D.link_mentions("plain words", LCFG), [{"text": "plain words"}])

    def test_job_label_gets_parts(self):
        data = {"projects": [{"id": "p", "name": "P", "jobs": [job(label="Backfill ENG-9")]}]}
        v = view(data=data, cfg={"tz": "America/Chicago", "tracker_url": "https://tracker.example.com/browse/"})
        self.assertEqual(v["jobs"]["p"][0]["label_parts"][1]["url"], "https://tracker.example.com/browse/ENG-9")

    def test_duplicates_collapse(self):
        data = {"projects": [{"id": "p", "name": "P", "summary": "ENG-1 and ENG-1", "needs_me": [{"ask": "ENG-1", "ticket": "ENG-1"}]}]}
        self.assertEqual(len(view(data=data)["unlinked"]), 1)


class DashboardView(unittest.TestCase):
    def test_view_has_dashboard_keys(self):
        data = {"projects": [proj("a", deadline="2026-01-20", jobs=[job()])], "waiting_on": [{"person": "Ana", "since": "2026-01-10"}]}
        v = view(data=data, feeds={"github": gh(my_prs=[pr(1)])})
        for k in ("timeline", "pipeline", "waiting", "delivered", "jobs", "stats", "unlinked", "projects", "waiting_on", "one_offs"):
            self.assertIn(k, v)
        self.assertEqual(v["jobs"]["a"][0]["label"], "Backfill")
        self.assertEqual([e["kind"] for e in v["timeline"]["events"]], ["deadline", "job"])
        self.assertEqual(v["waiting"]["rows"][0]["days"], 4)
        self.assertEqual(v["pipeline"]["stages"][1]["n"], 1)
        self.assertEqual(list(v["project_timelines"]), ["a"])


class Focus(unittest.TestCase):
    """focus_view: the one-screen home (hero, up next, running, wins, parked, feed note)."""

    def test_done_today_in_inbox_hides_the_same_open_line(self):
        data = {"projects": [], "one_offs": [{"title": "Sign two forms", "needs_me": True}, {"title": "Book travel", "needs_me": True}]}
        inbox = {"items": [{"id": "t1", "kind": "todo", "title": "Sign two forms", "done_at": "2026-01-14T15:00:00Z"}]}
        v = view(data=data, inbox=inbox)
        self.assertEqual([i["title"] for i in v["inbox"]["items"]], ["Book travel"])
        self.assertIn("Sign two forms", [d["title"] for d in v["inbox"]["done_today"]])

    def test_done_on_an_earlier_day_does_not_hide(self):
        data = {"projects": [], "one_offs": [{"title": "Sign two forms", "needs_me": True}]}
        inbox = {"items": [{"id": "t1", "kind": "todo", "title": "Sign two forms", "done_at": "2026-01-10T15:00:00Z"}]}
        self.assertEqual(len(view(data=data, inbox=inbox)["inbox"]["items"]), 1)

    def test_hero_up_next_and_parked(self):
        inbox = {"items": [
            {"id": "a", "kind": "todo", "title": "Nudge Ana: the export file", "due": "2026-01-13",
             "link": "https://tracker.example.com/browse/ENG-9"},
            {"id": "b", "kind": "todo", "title": "Idea: a new report"},
            {"id": "c", "kind": "todo", "title": "Plan the spring work", "due": "2026-03-01"},
            {"id": "d", "kind": "todo", "title": "Approve the agent"},
        ]}
        f = view(inbox=inbox, cfg={"tz": "America/Chicago", "tracker_url": "https://tracker.example.com/browse/"})["focus"]
        self.assertEqual(f["hero"]["action"], "Nudge Ana")
        self.assertEqual(f["hero"]["open_label"], "Open ENG-9")
        self.assertTrue(f["hero"]["late"])
        self.assertEqual(f["hero"]["when"], "1 day late")
        self.assertEqual([r["title"] for r in f["up_next"]], ["Approve the agent"])
        self.assertEqual(sorted(r["title"] for r in f["parked"]), ["Idea: a new report", "Plan the spring work"])
        self.assertEqual((f["needs"], f["late"]), (2, 1))

    def test_nothing_needs_you(self):
        self.assertIsNone(view()["focus"]["hero"])

    def test_confirm_runs_and_staged_milestone_shows_its_position(self):
        data = {"projects": [{"id": "a", "name": "A", "next_milestone": "Backfill chunk 2 of 4 copying. More later.",
                              "next_milestone_date": "2026-01-14"}]}
        inbox = {"items": [{"id": "c", "kind": "confirm", "title": "Confirm Ana got it", "since": "2026-01-10", "due": "2026-01-17"}]}
        f = view(data=data, inbox=inbox)["focus"]
        self.assertIsNone(f["hero"])
        kinds = [(r["kind"], r["step"]) for r in f["running"]]
        self.assertIn(("today", "chunk 2 of 4"), kinds)
        self.assertIn(("delivered", "day 4 of 7"), kinds)

    def test_old_feed_gets_a_note_and_marks_its_rows(self):
        old = gh(my_prs=[pr(5, review_decision="CHANGES_REQUESTED")], gen="2026-01-12T17:00:00Z")
        f = view(feeds={"github": old})["focus"]
        self.assertEqual(f["feed_note"]["sources"], ["github"])
        self.assertIn("GitHub feed last refreshed 01-12", f["feed_note"]["text"])
        self.assertTrue(f["hero"]["feed_old"])
        fresh = view(feeds={"github": gh(my_prs=[pr(5, review_decision="CHANGES_REQUESTED")])})["focus"]
        self.assertIsNone(fresh["feed_note"])
        self.assertFalse(fresh["hero"]["feed_old"])

    def test_wins_take_todays_progress_and_skip_status_lines(self):
        data = {"projects": [{"id": "a", "name": "A", "recent_progress": [
            {"date": "2026-01-14", "text": "ENG-1 shipped to prod. Notes follow."},
            {"date": "2026-01-14", "text": "No new chunk has landed yet."},
            {"date": "2026-01-13", "text": "Old win."}]}]}
        f = view(data=data)["focus"]
        self.assertEqual([w["title"] for w in f["wins"]], ["ENG-1 shipped to prod."])

    def test_hero_keeps_plain_detail_text(self):
        inbox = {"items": [{"id": "a", "kind": "todo", "title": "Nudge Ana: the export file"}]}
        hero = view(inbox=inbox)["focus"]["hero"]
        self.assertEqual(hero["detail"], "the export file")

    def test_late_or_due_today_never_parks(self):
        inbox = {"items": [
            {"id": "a", "kind": "todo", "title": "Idea: late one", "due": "2026-01-12"},
            {"id": "b", "kind": "todo", "title": "Idea: due now", "due": "2026-01-14"},
            {"id": "c", "kind": "todo", "title": "Idea: someday"},
        ]}
        cfg = {"tz": "America/Chicago", "focus": {"parked_patterns": ["^Idea\\b"]}}
        f = view(inbox=inbox, cfg=cfg)["focus"]
        self.assertEqual([r["title"] for r in f["parked"]], ["Idea: someday"])
        self.assertEqual((f["needs"], f["late"]), (2, 1))

    def test_snoozed_parks_with_wake_date(self):
        inbox = {"items": [{"id": "s", "kind": "todo", "title": "Read the RFC", "snooze_until": "2026-01-20"}]}
        f = view(inbox=inbox)["focus"]
        self.assertEqual([(r["title"], r["when"], r["snoozed"]) for r in f["parked"]], [("Read the RFC", "back 01-20", True)])

    def test_open_oneoff_not_for_you_runs(self):
        data = {"projects": [], "one_offs": [{"title": "Vendor sends the file", "state": "in progress"},
                                             {"title": "Old thing", "state": "done"}]}
        f = view(data=data)["focus"]
        self.assertEqual([(r["kind"], r["title"], r["step"]) for r in f["running"]],
                         [("oneoff", "Vendor sends the file", "in progress")])

    def test_done_today_needs_matching_ref_when_both_have_one(self):
        data = {"projects": [], "one_offs": [
            {"title": "Reply to Ana", "needs_me": True, "ref": "https://example.com/thread/2"}]}
        other = {"items": [{"id": "t", "kind": "todo", "title": "Reply to Ana", "link": "https://example.com/thread/1",
                            "done_at": "2026-01-14T15:00:00Z"}]}
        self.assertEqual(len(view(data=data, inbox=other)["inbox"]["items"]), 1)
        same = {"items": [{"id": "t", "kind": "todo", "title": "Reply to Ana", "link": "https://example.com/thread/2",
                           "done_at": "2026-01-14T15:00:00Z"}]}
        self.assertEqual(len(view(data=data, inbox=same)["inbox"]["items"]), 0)

    def test_late_confirm_is_not_also_running(self):
        inbox = {"items": [{"id": "c", "kind": "confirm", "title": "Confirm Ana got it", "since": "2026-01-05", "due": "2026-01-10"}]}
        f = view(inbox=inbox)["focus"]
        self.assertEqual(f["hero"]["title"], "Confirm Ana got it")
        self.assertNotIn("delivered", [r["kind"] for r in f["running"]])

    def test_running_milestone_shows_its_position(self):
        def step_of(text):
            data = {"projects": [{"id": "a", "name": "A", "next_milestone": text, "next_milestone_date": "2026-01-14"}]}
            r = [r for r in view(data=data)["focus"]["running"] if r["kind"] == "today"][0]
            return r["step"], r["done"], r["total"], r["pct"]
        self.assertEqual(step_of("Backfill chunk 2 of 4 copying."), ("chunk 2 of 4", 1, 4, None))
        self.assertEqual(step_of("Copy 3 of 10 files to the bucket."), ("3 of 10 files", None, None, 30))
        self.assertEqual(step_of("May chunk 1 copying, due 19:50Z."), ("chunk 1", None, None, None))
        self.assertEqual(step_of("Ship the release."), ("today", None, None, None))

    def test_running_job_shows_done_of_total(self):
        data = {"projects": [{"id": "p", "name": "P", "jobs": [{"label": "Backfill", "done": 3, "total": 10, "unit": "files"}]}]}
        steps = [r["step"] for r in view(data=data)["focus"]["running"] if r["kind"] == "job"]
        self.assertTrue(steps[0].startswith("3 of 10 files"), steps)

    def test_job_without_done_reads_zero(self):
        data = {"projects": [{"id": "p", "name": "P", "jobs": [{"label": "Backfill", "total": 100, "unit": "rows"}]}]}
        steps = [r["step"] for r in view(data=data)["focus"]["running"] if r["kind"] == "job"]
        self.assertTrue(steps and steps[0].startswith("0 of 100 rows"), steps)

    def test_explicit_zero_settings_and_effort_stay_zero(self):
        inbox = {"items": [{"id": "a", "kind": "todo", "title": "Tiny", "effort_min": 0}]}
        f = view(inbox=inbox, cfg={"tz": "America/Chicago", "focus": {"cap": 0, "up_next": 0}})["focus"]
        self.assertEqual((f["cap"], f["up_next_shown"]), (0, 0))
        self.assertEqual(f["hero"]["minutes"], 0)


if __name__ == "__main__":
    unittest.main()
