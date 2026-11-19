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


if __name__ == "__main__":
    unittest.main()
