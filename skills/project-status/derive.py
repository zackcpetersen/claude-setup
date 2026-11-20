"""Turn project data, the session inbox and the feed files into the page's inbox view.

Pure functions only: no file access, no clock. build.py loads the files and passes `now`.
Every rule about inbox items lives here (refs, ids, effort, bands, order, dedupe, snooze,
stale, done today, source freshness) so the page and the scripts stay simple.
"""
import copy
import hashlib
import math
import os
import re
from datetime import date, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python older than 3.9
    ZoneInfo = None

# Every config key is optional. bin/status-feeds keeps its own copy of the shared
# "inbox" and "feeds" keys (it is installed on its own); a test checks they match.
DEFAULTS = {
    "tz": "",
    "inbox": {
        "cap": 7,
        "home_count": 3,
        "stale_days": 7,
        "github_orgs": [],
        "review_teams": [],
        "slack_triage_log": "~/.claude/slack-poll-triage.jsonl",
        "slack_lookback_days": 3,
        "slack_url": "",
        "effort_defaults": {},
        "no_ci_repos": [],
    },
    "feeds": {"every_minutes": 15, "hours": "08:00-18:00", "days": "Mon-Fri"},
    # links.patterns: [{"match": "<regex with one group>", "url": "<base>{1}"}] for other keys a user names.
    # links.ticket_keys: tracker project keys ("ENG"); empty links any KEY-123 except standards like UTF-8.
    # links.repos: repo names a "repo #123" mention may name, on top of the repos in the GitHub feed.
    "links": {"patterns": [], "ticket_keys": [], "repos": []},
}

EFFORT = {"merge": 2, "send-draft": 2, "approve-agent": 2, "slack": 5, "nudge": 5, "confirm": 5, "todo": 5,
          "fix-ci": 15, "reply-review": 15, "conflict": 15, "ask": 15, "oneoff": 15}
PR_FIX_KINDS = ("conflict", "fix-ci", "reply-review")
SOURCE_RANK = {"session": 0, "projects": 1, "github": 2, "slack": 3}
SCRIPT_SOURCES = ("github", "slack")
BAND_LABELS = {1: "Late or today", 2: "Waiting on you", 3: "Quick wins", 4: "Your PR fixes", 5: "Everything else"}
SOURCE_LABELS = {"projects": "Projects", "session": "Session", "github": "GitHub", "slack": "Slack", "stats": "Stats"}
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

TIMELINE_DAYS = 21
TIMELINE_EVENTS = 12
SOON_DAYS = 3
JOB_STALE_DAYS = 2
WAIT_SCALE_MIN = 14
STATS_STALE_HOURS = 30


# ---------- config and time ----------

def settings(cfg):
    """Config merged over DEFAULTS, one level deep for the dict sections."""
    out = copy.deepcopy(DEFAULTS)
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def local_tz(name):
    """The IANA zone from config, else the system zone by name (so the page can format times), else a fixed offset."""
    candidates = [name, os.environ.get("TZ", "").lstrip(":")]
    real = os.path.realpath("/etc/localtime")
    if "zoneinfo/" in real:
        candidates.append(real.split("zoneinfo/", 1)[1])
    for c in candidates:
        if c and ZoneInfo is not None:
            try:
                return ZoneInfo(c)
            except Exception:
                continue
    return datetime.now().astimezone().tzinfo


def parse_time(value, tz=timezone.utc):
    """Lenient ISO parse: 'Z' or an offset, with or without seconds, or a bare date.
    A value without a zone is read in `tz`. Returns an aware datetime or None."""
    if not value or not isinstance(value, str):
        return None
    t = value.strip()
    if t.endswith("Z") or t.endswith("z"):
        t = t[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        try:
            d = datetime.combine(date.fromisoformat(t[:10]), time())
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=tz)


def parse_day(value):
    """The YYYY-MM-DD at the start of a value, or None."""
    if isinstance(value, str) and re.match(r"^\d{4}-\d\d-\d\d", value):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def sha(text, n=10):
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:n]


def hid_of(item_id):
    return sha(item_id, 8)


# ---------- refs and effort ----------

GH_PR = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
SLACK_URL = re.compile(r"^https://[^/\s]+\.slack\.com/archives/([A-Z0-9]+)/p(\d{10})(\d{6})")
SLACK_KEY = re.compile(r"^([A-Z0-9]+):(\d{10}\.\d{6})$")


def make_ref(link):
    """Canonical dedupe key, built only from a link (or a Slack triage key). Ticket keys never count."""
    if not link or not isinstance(link, str):
        return ""
    link = link.strip()
    m = GH_PR.match(link)
    if m:
        return f"gh:{m.group(1)}/{m.group(2)}#{m.group(3)}"
    m = SLACK_URL.match(link)
    if m:
        return f"slack:{m.group(1)}:{m.group(2)}.{m.group(3)}"
    m = SLACK_KEY.match(link)
    if m:
        return f"slack:{m.group(1)}:{m.group(2)}"
    if link.startswith("https://"):
        return "url:" + re.split(r"[?#]", link, maxsplit=1)[0]
    return ""


def canonical_ref(ref):
    """A ref given as a URL or Slack key becomes its canonical form (so it merges with the feeds); others stay as given."""
    ref = str(ref or "").strip()
    return make_ref(ref) or ref


def parse_effort(value):
    """'5m', '1h', '1h 10m', 15 or '15' to minutes. None when it cannot be read."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, int(value))
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    m = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?", text)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def effort_label(minutes):
    minutes = int(minutes or 0)
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h" + (f" {m}m" if m else "")


def default_effort(kind, lines=None, overrides=None):
    overrides = overrides or {}
    if kind in overrides:
        got = parse_effort(overrides[kind])
        if got is not None:
            return got
    if kind == "review":
        n = lines or 0
        return 15 if n < 100 else 30 if n < 500 else 60
    return EFFORT.get(kind, 15)


def truncate(text, n=90):
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0] or text[:n]
    return cut.rstrip(" ,;:.") + "..."


# ---------- items from each source ----------

def _item(**kw):
    base = {"id": "", "kind": "", "title": "", "why": "", "link": "", "ref": "", "project_id": "",
            "since": None, "due": None, "effort_min": None, "who_waits": "", "source": ""}
    base.update({k: v for k, v in kw.items() if v is not None})
    base["ref"] = canonical_ref(base["ref"]) if base["ref"] else make_ref(base["link"])
    return base


def project_items(data, today):
    """Asks from projects[].needs_me, needs-me one-offs, and nudges due today or earlier."""
    out = []
    for p in data.get("projects") or []:
        pid = p.get("id", "")
        used = set()
        for n in p.get("needs_me") or []:
            ask = n.get("ask") or ""
            key = n.get("ticket") or ""
            if not key or key in used:
                key = sha(ask)
            used.add(key)
            it = _item(kind="ask", title=ask, why=n.get("why") or "", link=n.get("link") or "", project_id=pid,
                       due=n.get("due") or None, effort_min=parse_effort(n.get("effort")),
                       who_waits=n.get("who_waits") or "", source="projects", ticket=n.get("ticket") or "",
                       from_needs_me=True)
            it["id"] = it["ref"] or f"proj:{pid}:{key}"
            out.append(it)
    used_oneoff = {}
    for o in data.get("one_offs") or []:
        if not o.get("needs_me") or str(o.get("state", "")).lower() == "done":
            continue
        link = o.get("ref") if str(o.get("ref") or "").startswith("https://") else ""
        it = _item(kind="oneoff", title=o.get("title") or "", why=o.get("note") or "", link=link,
                   due=o.get("due") or None, source="projects")
        base_id = "oneoff:" + sha(o.get("title") or "")
        n = used_oneoff.get(base_id, 0)
        used_oneoff[base_id] = n + 1
        # Same title twice: the second gets its place among same-titled items, so ids never collide.
        it["id"] = it["ref"] or (base_id if n == 0 else f"{base_id}:{n + 1}")
        out.append(it)
    for w in data.get("waiting_on") or []:
        nd = parse_day(w.get("nudge_due"))
        if not nd or nd > today:
            continue
        person = w.get("person") or "someone"
        it = _item(kind="nudge", title=f"Nudge {person}: {w.get('what') or ''}".strip().rstrip(":"),
                   why=w.get("where") or "", link=w.get("link") or "", project_id=w.get("project_id") or "",
                   since=w.get("since") or None, due=w.get("nudge_due"), source="projects")
        it["id"] = it["ref"] or f"nudge:{w.get('project_id') or ''}:{person}:{sha(w.get('what') or '', 8)}"
        out.append(it)
    return out


def session_items(inbox, today):
    """Open items from inbox.json, split into (shown, snoozed). Done items are left out."""
    shown, snoozed = [], []
    for s in (inbox or {}).get("items") or []:
        if s.get("done_at"):
            continue
        it = _item(kind=s.get("kind") or "todo", title=s.get("title") or "", why=s.get("why") or "",
                   link=s.get("link") or "", ref=s.get("ref") or "", project_id=s.get("project_id") or "",
                   since=s.get("since") or None, due=s.get("due") or None,
                   effort_min=parse_effort(s.get("effort_min", s.get("effort"))),
                   who_waits=s.get("who_waits") or "", source="session")
        it["id"] = it["ref"] or "s:" + str(s.get("id") or sha(it["title"]))
        su = parse_day(s.get("snooze_until"))
        if su and su > today:
            it["snooze_until"] = su.isoformat()
            snoozed.append(it)
        else:
            shown.append(it)
    return shown, snoozed


def pr_kind(pr, no_ci_repos=()):
    """The one inbox item for one of my open PRs, as (kind, why), or None. Never infers from UNKNOWN or null.

    "Merge" needs checks that passed (ci SUCCESS). A null rollup usually means checks have not reported yet
    (right after a push), so it only counts as green for repos listed in inbox.no_ci_repos (repos with no checks).
    """
    if pr.get("draft"):
        return None
    ci = pr.get("ci")
    if pr.get("mergeable") == "CONFLICTING":
        return "conflict", "Merge conflict"
    if ci in ("FAILURE", "ERROR"):
        return "fix-ci", "CI failed"
    threads = pr.get("unresolved_threads") or 0
    if pr.get("review_decision") == "CHANGES_REQUESTED":
        return "reply-review", "Changes requested"
    if threads > 0:
        return "reply-review", f"{threads} open thread" + ("s" if threads != 1 else "")
    green = ci == "SUCCESS" or (ci is None and pr.get("repo") in set(no_ci_repos or ()))
    if (pr.get("review_decision") == "APPROVED" and green
            and pr.get("merge_state") not in ("BLOCKED", "DIRTY", "BEHIND")):
        return "merge", "Approved, merge check pending" if pr.get("mergeable") == "UNKNOWN" else "Approved and green"
    return None


PR_VERB = {"conflict": "Fix conflict", "fix-ci": "Fix CI", "reply-review": "Reply to review", "merge": "Merge"}


def github_items(feed, overrides, no_ci_repos=()):
    out = []
    if not feed:
        return out
    for pr in feed.get("my_prs") or []:
        got = pr_kind(pr, no_ci_repos)
        if not got:
            continue
        kind, why = got
        out.append(_item(kind=kind, title=f"{PR_VERB[kind]}: {pr.get('title', '')}", why=why, link=pr.get("url") or "",
                         since=pr.get("created_at"), effort_min=default_effort(kind, None, overrides), source="github",
                         _first_seen_wins=True))
    for rq in feed.get("review_requests") or []:
        lines = (rq.get("additions") or 0) + (rq.get("deletions") or 0)
        out.append(_item(kind="review", title=f"Review: {rq.get('title', '')}",
                         why=f"{rq.get('author') or 'Someone'} asked, {lines} lines", link=rq.get("url") or "",
                         since=rq.get("requested_at") or rq.get("created_at"),
                         effort_min=default_effort("review", lines, overrides), who_waits=rq.get("author") or "",
                         source="github"))
    for it in out:
        it["id"] = it["ref"] or "gh:" + it["link"]
    return out


def slack_items(feed, slack_url, overrides):
    out = []
    for a in (feed or {}).get("asks") or []:
        ch, ts = a.get("channel") or "", a.get("ts") or ""
        base = slack_url.rstrip("/") + "/" if slack_url else ""
        link = f"{base}{ch}/p{ts.replace('.', '')}" if base and ch and ts else ""
        it = _item(kind="slack", title="Reply: " + truncate(a.get("reason") or "Slack message"), link=link,
                   ref=f"slack:{ch}:{ts}" if ch and ts else make_ref(a.get("key") or ""), since=a.get("at"),
                   effort_min=default_effort("slack", None, overrides), source="slack")
        it["id"] = it["ref"] or "slack:" + str(a.get("key"))
        out.append(it)
    return out


# ---------- merge, band, order ----------

def dedupe(items):
    """Items with the same ref become one. Words come from the highest source, live state from a script source."""
    groups, order = {}, []
    for it in items:
        k = it["ref"] or ("\0" + it["id"] + "\0" + str(len(order)))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(it)
    out = []
    for k in order:
        g = sorted(groups[k], key=lambda i: SOURCE_RANK.get(i["source"], 9))
        if len(g) == 1:
            g[0]["sources"] = [g[0]["source"]]
            out.append(g[0])
            continue
        top = dict(g[0])
        top["sources"] = sorted({i["source"] for i in g}, key=lambda s: SOURCE_RANK.get(s, 9))
        if any(i.get("from_needs_me") for i in g):
            top["from_needs_me"] = True
        live = next((i for i in g if i["source"] in SCRIPT_SOURCES), None)
        if live:
            for f in ("kind", "link", "effort_min", "source"):
                if live.get(f) not in (None, ""):
                    top[f] = live[f]
        for f in ("title", "why", "project_id", "who_waits"):
            if not top.get(f):
                top[f] = next((i[f] for i in g if i.get(f)), top.get(f))
        sinces = [i["since"] for i in g if i.get("since")]
        top["since"] = min(sinces, key=lambda v: parse_time(v) or datetime.max.replace(tzinfo=timezone.utc)) if sinces else None
        dues = [i["due"] for i in g if parse_day(i.get("due"))]
        top["due"] = min(dues, key=parse_day) if dues else None
        top["id"] = top["ref"]
        if any(i.get("snooze_until") for i in g):
            top["snooze_until"] = max(i["snooze_until"] for i in g if i.get("snooze_until"))
        out.append(top)
    return out


def age_label(since, now, tz):
    d = parse_time(since, tz)
    if not d:
        return ""
    n = (now.astimezone(tz).date() - d.astimezone(tz).date()).days
    if n <= 0:
        return "today"
    return f"{n}d" if n < 14 else f"{n // 7}w"


def finish(it, today, now, tz, st, overrides):
    """Fill the computed fields: effort, band, late, due_today, stale, age, hid."""
    if it.get("effort_min") is None:
        it["effort_min"] = default_effort(it["kind"], None, overrides)
    it["effort"] = effort_label(it["effort_min"])
    due = parse_day(it.get("due"))
    it["due"] = due.isoformat() if due else None
    it["late"] = bool(due and due < today)
    it["due_today"] = bool(due and due == today)
    if due and due <= today:
        band = 1
    elif it.get("who_waits") or it["kind"] in ("review", "slack"):
        band = 2
    elif it["effort_min"] <= 5:
        band = 3
    elif it["kind"] in PR_FIX_KINDS:
        band = 4
    else:
        band = 5
    it["band"] = band
    since = parse_time(it.get("since"), tz)
    it["since"] = iso(since)
    it["stale"] = bool(not due and since and now - since > timedelta(days=st))
    it["age"] = age_label(it["since"], now, tz)
    it["hid"] = hid_of(it["id"])
    it.pop("ticket", None)
    return it


def sort_key(it):
    since = parse_time(it.get("since")) or datetime.max.replace(tzinfo=timezone.utc)
    return (it["band"], it["effort_min"], since, it["title"].lower())


# ---------- freshness ----------

def parse_hours(text):
    m = re.fullmatch(r"\s*(\d\d?):(\d\d)\s*-\s*(\d\d?):(\d\d)\s*", str(text or ""))
    if not m:
        return time(0, 0), time(23, 59, 59)
    return time(int(m.group(1)), int(m.group(2))), time(int(m.group(3)), int(m.group(4)))


def parse_days(text):
    """'Mon-Fri', 'Mon,Wed,Fri' or 'Mon-Sun' to a set of weekday numbers (Monday is 0)."""
    out = set()
    for part in str(text or "Mon-Sun").lower().replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a[:3] in DAY_NAMES and b[:3] in DAY_NAMES:
                i, j = DAY_NAMES.index(a[:3]), DAY_NAMES.index(b[:3])
                k = i
                while True:
                    out.add(k)
                    if k == j:
                        break
                    k = (k + 1) % 7
        elif part[:3] in DAY_NAMES:
            out.add(DAY_NAMES.index(part[:3]))
    return out or set(range(7))


def in_hours_minutes(start, end, tz, hours, days):
    """Minutes between two times that fall inside the scheduled hours and days, local time."""
    if end <= start:
        return 0.0
    h0, h1 = hours
    s, e = start.astimezone(tz), end.astimezone(tz)
    total, d = 0.0, s.date()
    while d <= e.date():
        if d.weekday() in days:
            lo = datetime.combine(d, h0, tzinfo=tz)
            hi = datetime.combine(d, h1, tzinfo=tz)
            a, b = max(lo, s), min(hi, e)
            if b > a:
                total += (b - a).total_seconds() / 60
        d += timedelta(days=1)
    return total


def source_state(name, feed, err, cfg, now, tz):
    """One source's page state: ok, stale, failing or missing."""
    st = {"name": name, "label": SOURCE_LABELS.get(name, name), "state": "missing", "as_of": None, "error": None,
          "last_ok_at": None}
    if err:
        st.update(state="failing", error=err)
        return st
    if feed is None:
        return st
    gen = parse_time(feed.get("generated_at") or feed.get("updated_at"))
    if gen:
        local = gen.astimezone(tz)
        st["as_of"] = local.strftime("%H:%M" if local.date() == now.astimezone(tz).date() else "%m-%d %H:%M")
    st["last_ok_at"] = feed.get("last_ok_at")
    if feed.get("ok") is False:
        st.update(state="failing", error=feed.get("error") or "failed")
        return st
    st["state"] = "ok"
    if name == "stats":
        # Stats refresh once a day, so the in-hours rule for the live feeds does not fit.
        if gen and now - gen > timedelta(hours=STATS_STALE_HOURS):
            st["state"] = "stale"
        return st
    if name in SCRIPT_SOURCES and gen:
        fd = cfg["feeds"]
        every = float(fd.get("every_minutes") or 15)
        mins = in_hours_minutes(gen, now, tz, parse_hours(fd.get("hours")), parse_days(fd.get("days")))
        if mins >= 2 * every:
            st["state"] = "stale"
    return st


# ---------- done today ----------

def _local_day(value, tz):
    d = parse_time(value, tz)
    return d.astimezone(tz).date() if d else None


def done_today(prev, open_now, snoozed_now, inbox, feeds, gh_ok_now, today, now, tz):
    """Items cleared from the inbox today, and the cleared list to keep in state."""
    cleared = list(prev.get("cleared") or []) if prev.get("date") == today.isoformat() else []
    open_ids = set(open_now) | set(snoozed_now)
    cleared = [c for c in cleared if c.get("id") not in open_ids]
    seen = {c.get("id") for c in cleared}
    gh = feeds.get("github") or {}
    # Absence alone proves little (CI back to pending, a draft, the result cap), so a GitHub item counts as
    # cleared only when the feed shows why: my PR merged, or a review request no longer aimed at the user.
    merged_refs = {make_ref(m.get("url") or "") for m in gh.get("merged_recent") or []}
    asked_refs = {make_ref(r.get("url") or "") for r in gh.get("review_requests") or []}
    if (prev.get("date") == today.isoformat() and (prev.get("sources_ok") or {}).get("github") and gh_ok_now
            and not gh.get("truncated")):
        for pid, p in (prev.get("open") or {}).items():
            if pid in open_ids or pid in seen or not pid.startswith("gh:") or p.get("snoozed"):
                continue
            if p.get("source") != "github":  # projects and session items are never counted by absence
                continue
            if not (pid in merged_refs if p.get("kind") != "review" else pid not in asked_refs):
                continue
            cleared.append({"id": pid, "title": p.get("title", ""), "ref": p.get("ref") or pid, "at": iso(now)})
            seen.add(pid)
    shown = [dict(c) for c in cleared]
    refs = {c.get("ref") or c.get("id") for c in shown}

    def add(title, ref, at):
        if ref and ref in refs:
            return
        if ref:
            refs.add(ref)
        shown.append({"id": ref or "", "title": title, "ref": ref or "", "at": at})

    for s in (inbox or {}).get("items") or []:
        if s.get("done_at") and _local_day(s["done_at"], tz) == today:
            add(s.get("title") or "", s.get("ref") or make_ref(s.get("link")) or "s:" + str(s.get("id")), s["done_at"])
    for c in ((feeds.get("slack") or {}).get("cleared") or []):
        if _local_day(c.get("at"), tz) == today:
            add("Reply: " + truncate(c.get("reason") or "Slack message"), make_ref(c.get("key") or ""), c.get("at"))
    for m in ((feeds.get("github") or {}).get("merged_recent") or []):
        if _local_day(m.get("merged_at"), tz) == today:
            add("Merged: " + (m.get("title") or ""), make_ref(m.get("url") or ""), m.get("merged_at"))
    return shown, cleared


# ---------- dashboard views: jobs, timeline, pipeline, waiting, deliveries ----------

def _num(v):
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _count_text(n):
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,.1f}"


def job_views(project, today, tz):
    """The project's long jobs with percent, finish date, staleness and lateness worked out."""
    out = []
    for j in project.get("jobs") or []:
        done, total, per_day = _num(j.get("done")) or 0.0, _num(j.get("total")), _num(j.get("per_day"))
        finished = bool(total and total > 0 and done >= total)
        pct = max(0, min(100, math.floor(100 * done / total))) if total else None
        upd = _local_day(j.get("updated"), tz)
        eta, src = parse_day(j.get("eta")), None
        if eta:
            src = "given"
        elif per_day and per_day > 0 and total and not finished:
            # Counted from the last report, so a job that stops reporting goes late instead of sliding.
            eta, src = (upd or today) + timedelta(days=math.ceil((total - done) / per_day)), "computed"
        unit = str(j.get("unit") or "").strip()
        left = None
        if total is not None:
            left = _count_text(max(0.0, total - done)) + (" " + unit if unit else "")
        out.append({
            "label": j.get("label") or "", "done": j.get("done"), "total": j.get("total"), "unit": unit, "pct": pct,
            "per_day": j.get("per_day"), "eta": eta.isoformat() if eta else None, "eta_source": src,
            "updated": j.get("updated"), "stale": bool(upd and (today - upd).days > JOB_STALE_DAYS),
            "late": bool(eta and eta < today and not finished), "finished": finished, "left": left,
        })
    return out


def _rank(priority):
    m = re.search(r"\d", str(priority or ""))
    return int(m.group(0)) if m else 9


def timeline_view(projects, jobs_by_id, today, project_id=None):
    """Dated events in the next TIMELINE_DAYS days on one axis. Passed dates stay, pinned late at day 0."""
    end = today + timedelta(days=TIMELINE_DAYS - 1)
    events = []
    for p in projects or []:
        pid = p.get("id", "")
        if project_id is not None and pid != project_id:
            continue
        name = p.get("name") or pid
        cand = [("deadline", p.get("deadline"), "Deadline", "")]
        if p.get("next_milestone_date"):
            cand.append(("milestone", p.get("next_milestone_date"), truncate(p.get("next_milestone") or "Milestone", 40), ""))
        for n in p.get("needs_me") or []:
            cand.append(("ask", n.get("due"), truncate(n.get("ask") or "Ask", 40), n.get("link") or ""))
        for j in (jobs_by_id or {}).get(pid) or []:
            if not j.get("finished"):
                cand.append(("job", j.get("eta"), f"{j.get('label') or 'Job'} done", ""))
        for kind, when, label, link in cand:
            d = parse_day(when)
            if not d or d > end:
                continue
            day = (d - today).days
            events.append({"kind": kind, "date": d.isoformat(), "label": label, "sub": name, "project_id": pid,
                           "link": link, "day": max(0, day), "late": day < 0, "soon": 0 <= day <= SOON_DAYS,
                           "_sort": (max(0, day), _rank(p.get("priority")), name.lower())})
    events.sort(key=lambda e: e["_sort"])
    for e in events:
        e.pop("_sort")
    return {"from": today.isoformat(), "to": end.isoformat(), "days": TIMELINE_DAYS,
            "more": max(0, len(events) - TIMELINE_EVENTS), "events": events[:TIMELINE_EVENTS]}


STATS_KEYS = ("generated_at", "ok", "error", "last_ok_at", "login", "org", "team", "coverage", "groups", "excluded")
PIPE_STAGES = (("draft", "Draft"), ("review", "In review"), ("approved", "Approved"), ("merged", "Merged this week"))


def _pill(pr):
    repo = str(pr.get("repo") or "").split("/")[-1]
    return {"label": f"{repo}#{pr.get('number')}", "title": pr.get("title") or "", "url": pr.get("url") or "",
            "ci_failed": pr.get("ci") in ("FAILURE", "ERROR"), "conflict": pr.get("mergeable") == "CONFLICTING"}


def pipeline_view(gh, gh_ok=True):
    """My PRs by stage, from the GitHub feed. None when there is no feed; stale when the feed is failing."""
    if not gh:
        return None
    far = "9999"
    by = {k: [] for k, _ in PIPE_STAGES}
    for pr in sorted(gh.get("my_prs") or [], key=lambda x: x.get("created_at") or far):
        stage = "draft" if pr.get("draft") else "approved" if pr.get("review_decision") == "APPROVED" else "review"
        by[stage].append(_pill(pr))
    by["merged"] = [_pill(m) for m in sorted(gh.get("merged_recent") or [], key=lambda x: x.get("merged_at") or "",
                                              reverse=True)]
    return {"stages": [{"key": k, "label": lab, "n": len(by[k]), "pills": by[k]} for k, lab in PIPE_STAGES],
            "reviews_owed": len(gh.get("review_requests") or []), "stale": not gh_ok}


def waiting_view(waiting_on, today, tz):
    """Days waited and the nudge point for each waiting_on row, in order, on one shared scale."""
    rows = []
    for w in waiting_on or []:
        since, nd = _local_day(w.get("since"), tz), parse_day(w.get("nudge_due"))
        rows.append({"days": (today - since).days if since else None,
                     "nudge_at": (nd - since).days if since and nd else None,
                     "late": bool(nd and nd < today), "due_today": bool(nd and nd == today)})
    scale = max([WAIT_SCALE_MIN] + [r["days"] for r in rows if r["days"] is not None]
                + [r["nudge_at"] for r in rows if r["nudge_at"] is not None])
    return {"scale_days": scale, "rows": rows}


def delivered_view(items, snoozed, today, tz):
    """Deliveries waiting for a confirmation, with a countdown to their due date."""
    out = []
    for it in list(items or []) + list(snoozed or []):
        due = parse_day(it.get("due"))
        if it.get("kind") != "confirm" or not due:
            continue
        since = _local_day(it.get("since"), tz) or today
        total = max(1, (due - since).days)
        out.append({"hid": it.get("hid"), "title": it.get("title") or "", "link": it.get("link") or "",
                    "title_parts": it.get("title_parts"), "since": since.isoformat(), "due": due.isoformat(),
                    "total": total, "elapsed": max(0, min(total, (today - since).days)), "left": (due - today).days,
                    "late": due < today})
    out.sort(key=lambda r: r["due"])
    return out


# ---------- links for every mention ----------

TICKET_RE = r"(?<![A-Za-z0-9-])([A-Z][A-Z0-9]+)-\d+(?![A-Za-z0-9])"
# Standards and names shaped like a ticket key ("UTF-8", "SHA-256"); used only when links.ticket_keys is empty.
NOT_TICKETS = frozenset({"UTF", "SHA", "ISO", "COVID", "RFC", "CVE", "PEP", "IPV4", "IPV6", "HTTP", "TLS", "SSL",
                         "AES", "RSA", "MD", "MP", "GPT", "ES", "UTC", "GMT", "IEEE", "ANSI", "WCAG", "WPA", "EAN"})
REPO_REF_RE = r"(?<![\w/-])([a-z][a-z0-9-]+) #(\d+)\b"
SLACK_KEY_RE = r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{6,}):(\d{10}\.\d{6})(?!\d)"
URL_RE = r"https?://[^\s<>\"')\]]+"
THREAD_WORDS = re.compile(r"\b(slack|thread|notion|doc|docs)\b", re.I)


def _http(url):
    return url if isinstance(url, str) and re.match(r"^https?://", url.strip(), re.I) else None


def _bases(conf):
    tracker = str(conf.get("tracker_url") or "")
    org = str(conf.get("github_org") or "")
    slack = str((conf.get("inbox") or {}).get("slack_url") or "")
    ok = lambda v: bool(v) and "FILL-IN" not in v
    pats = []
    for p in ((conf.get("links") or {}).get("patterns") or []):
        try:
            if isinstance(p, dict) and p.get("match") and p.get("url"):
                pats.append((re.compile(p["match"]), str(p["url"])))
        except re.error:
            continue
    return (tracker if ok(tracker) else ""), (org if ok(org) else ""), (slack if ok(slack) else ""), pats


def _is_ticket(prefix, conf):
    keys = [str(k).upper() for k in ((conf.get("links") or {}).get("ticket_keys") or []) if k]
    return prefix in keys if keys else prefix not in NOT_TICKETS


def _known_repos(conf):
    """Repo names a "word #N" mention may name: links.repos plus the repos in the GitHub feed."""
    return {str(r).split("/")[-1] for r in ((conf.get("links") or {}).get("repos") or []) if r} | set(conf.get("_feed_repos") or ())


def _matches(text, conf):
    """Every mention in text as (start, end, kind, url or None), earliest first, no overlaps."""
    tracker, org, slack, pats = _bases(conf)
    repos = _known_repos(conf)
    found = []
    for m in re.finditer(URL_RE, text):
        u = m.group(0).rstrip(".,;:")
        found.append((m.start(), m.start() + len(u), "url", _http(u)))
    for m in re.finditer(TICKET_RE, text):
        if not _is_ticket(m.group(1), conf):
            continue
        found.append((m.start(), m.end(), "ticket", _http(tracker + m.group(0)) if tracker else None))
    for m in re.finditer(REPO_REF_RE, text):
        if m.group(1) not in repos:  # "chunk #2" or "step #3" is not a PR
            continue
        url = f"https://github.com/{org}/{m.group(1)}/pull/{m.group(2)}" if org else None
        found.append((m.start(), m.end(), "repo", url))
    for m in re.finditer(SLACK_KEY_RE, text):
        url = f"{slack.rstrip('/')}/{m.group(1)}/p{m.group(2).replace('.', '')}" if slack else None
        found.append((m.start(), m.end(), "slack", _http(url) if url else None))
    for rx, base in pats:
        for m in rx.finditer(text):
            if m.end() > m.start():
                val = m.group(1) if rx.groups else m.group(0)
                if not isinstance(val, str) or not val:  # an optional group that did not match
                    continue
                found.append((m.start(), m.end(), "pattern", _http(base.replace("{1}", val))))
    found.sort(key=lambda f: (f[0], -(f[1] - f[0])))
    out, pos = [], 0
    for f in found:
        if f[0] >= pos:
            out.append(f)
            pos = f[1]
    return out


def link_mentions(text, conf):
    """Plain text split into segments; mentions with a configured base carry a url."""
    text = str(text or "")
    segs, pos = [], 0
    for start, end, _kind, url in _matches(text, conf):
        if not url:
            continue
        if start > pos:
            segs.append({"text": text[pos:start]})
        segs.append({"text": text[start:end], "url": url})
        pos = end
    if pos < len(text):
        segs.append({"text": text[pos:]})
    return segs


WHY = {"ticket": "no tracker_url", "repo": "no github_org", "slack": "no inbox.slack_url", "pattern": "bad links.patterns url",
       "url": "not an http link"}


def _texts(data, view):
    """Every (where, text, row_link or None for rows that cannot hold one) the page shows."""
    out = []
    for p in data.get("projects") or []:
        base = f"projects.{p.get('id', '')}"
        for f in ("name", "epic", "summary", "next_milestone"):
            out.append((f"{base}.{f}", p.get(f), None))
        for i, n in enumerate(p.get("needs_me") or []):
            out.append((f"{base}.needs_me[{i}].ask", n.get("ask"), n.get("link") or ""))
            out.append((f"{base}.needs_me[{i}].ticket", n.get("ticket"), None))
            out.append((f"{base}.needs_me[{i}].why", n.get("why"), None))
        for gi, g in enumerate(p.get("breakdown") or []):
            for ii, it in enumerate(g.get("items") or []):
                ref = it.get("ref") or ""
                out.append((f"{base}.breakdown[{gi}].items[{ii}].text", it.get("text"), ref if _http(ref) else ""))
                out.append((f"{base}.breakdown[{gi}].items[{ii}].ref", None if _http(ref) else ref, None))
        for i, d in enumerate(p.get("decisions") or []):
            out.append((f"{base}.decisions[{i}].decision", d.get("decision"), None))
        for i, d in enumerate(p.get("recent_progress") or []):
            out.append((f"{base}.recent_progress[{i}].text", d.get("text"), None))
        for i, j in enumerate(p.get("jobs") or []):
            out.append((f"{base}.jobs[{i}].label", j.get("label"), None))
    for i, w in enumerate(data.get("waiting_on") or []):
        out.append((f"waiting_on[{i}].what", w.get("what"), w.get("link") or ""))
        out.append((f"waiting_on[{i}].where", w.get("where"), None))
    for i, o in enumerate(data.get("one_offs") or []):
        ref = o.get("ref") or ""
        out.append((f"one_offs[{i}].title", o.get("title"), ref if _http(ref) else ""))
        out.append((f"one_offs[{i}].note", o.get("note"), None))
        out.append((f"one_offs[{i}].ref", None if _http(ref) else ref, None))
    ib = view.get("inbox") or {}
    for i, it in enumerate((ib.get("items") or []) + (ib.get("snoozed") or [])):
        out.append((f"inbox.{it.get('hid')}.title", it.get("title"), it.get("link") or ""))
        out.append((f"inbox.{it.get('hid')}.why", it.get("why"), None))
    return out


def unlinked_mentions(view, data, inbox, conf):
    """Mentions the page cannot link: a key whose base is not configured, or a row naming a thread or page with no link."""
    del inbox  # inbox rows reach the page through view["inbox"]; kept in the signature for the board's callers
    seen, out = set(), []
    for where, text, row_link in _texts(data, view):
        if not text:
            continue
        text = str(text)
        for start, end, kind, url in _matches(text, conf):
            if url is None and text[start:end] not in seen:
                seen.add(text[start:end])
                out.append({"where": where, "text": text[start:end], "why": WHY[kind]})
        if row_link == "" and THREAD_WORDS.search(text) and text not in seen:
            seen.add(text)
            out.append({"where": where, "text": truncate(text, 60), "why": "names a thread or page but has no link"})
    return out


PART_FIELDS = {
    "project": ("name", "epic", "summary", "next_milestone"),
    "needs_me": ("ask", "ticket", "why"),
    "item": ("text", "ref"),
    "decision": ("decision",),
    "progress": ("text",),
    "wait": ("what", "where"),
    "oneoff": ("title", "note", "ref"),
    "inbox": ("title", "why"),
    "job": ("label",),
}


def add_parts(obj, kind, conf):
    """Adds <field>_parts next to each text field that holds at least one linkable mention."""
    for f in PART_FIELDS[kind]:
        v = obj.get(f)
        if isinstance(v, str) and v:
            segs = link_mentions(v, conf)
            if any(s.get("url") for s in segs):
                obj[f + "_parts"] = segs
    return obj


def linked_data(data, conf):
    """A copy of projects, waiting_on and one_offs with link segments added for the page."""
    projects = copy.deepcopy(data.get("projects") or [])
    for p in projects:
        add_parts(p, "project", conf)
        for n in p.get("needs_me") or []:
            add_parts(n, "needs_me", conf)
        for g in p.get("breakdown") or []:
            for it in g.get("items") or []:
                add_parts(it, "item", conf)
        for d in p.get("decisions") or []:
            add_parts(d, "decision", conf)
        for d in p.get("recent_progress") or []:
            add_parts(d, "progress", conf)
    waits = [add_parts(dict(w), "wait", conf) for w in data.get("waiting_on") or []]
    offs = [add_parts(dict(o), "oneoff", conf) for o in data.get("one_offs") or []]
    return projects, waits, offs


# ---------- the whole view ----------

def next_meeting(inbox, now, tz):
    m = (inbox or {}).get("next_meeting") or {}
    at = parse_time(m.get("at"), tz)
    if not at or at <= now or at.astimezone(tz).date() != now.astimezone(tz).date():
        return None
    return {"title": m.get("title") or "Meeting", "time": at.astimezone(tz).strftime("%H:%M"), "at": iso(at)}


def build_view(data, cfg, inbox, feeds, prev_state, now, errors=None):
    """Everything the page needs beyond the raw project data, plus the next build state.

    data: projects.json. cfg: config.json (any keys). inbox: inbox.json or None.
    feeds: {"github", "slack", "stats": dict or None}. prev_state: state/build.json or {}.
    now: aware datetime. errors: {"session"|"github"|"slack"|"stats": "parse error text"} for files that failed to load.
    Returns (view, state).
    """
    conf = settings(cfg)
    errors = errors or {}
    feeds = feeds or {}
    prev_state = prev_state or {}
    gh_feed = feeds.get("github") or {}
    conf["_feed_repos"] = {str(pr.get("repo") or "").split("/")[-1]
                           for k in ("my_prs", "review_requests", "merged_recent")
                           for pr in gh_feed.get(k) or [] if isinstance(pr, dict) and pr.get("repo")}
    tz = local_tz(conf.get("tz"))
    today = now.astimezone(tz).date()
    ib = conf["inbox"]
    overrides = ib.get("effort_defaults") or {}

    shown, snoozed = session_items(inbox, today)
    raw = shown + snoozed + project_items(data, today)
    raw += github_items(feeds.get("github"), overrides, ib.get("no_ci_repos") or [])
    raw += slack_items(feeds.get("slack"), ib.get("slack_url") or "", overrides)
    merged = dedupe(raw)

    prev_open = prev_state.get("open") or {}
    for it in merged:
        first = (prev_open.get(it["id"]) or {}).get("first_seen")
        # My PRs: updated_at moves on every push or comment, so the age runs from when the inbox first saw the item.
        if it.pop("_first_seen_wins", False) and first:
            it["since"] = first
        elif not it.get("since"):
            it["since"] = first or iso(now)
        finish(it, today, now, tz, ib.get("stale_days", 7), overrides)
    is_snoozed = lambda i: bool(i.get("snooze_until"))
    items = sorted([i for i in merged if not is_snoozed(i)], key=sort_key)
    later = sorted([i for i in merged if is_snoozed(i)], key=lambda i: (i["snooze_until"], i["title"].lower()))

    sources = [source_state("projects", {"ok": True, "generated_at": data.get("as_of")}, None, conf, now, tz),
               source_state("session", inbox, errors.get("session"), conf, now, tz),
               source_state("github", feeds.get("github"), errors.get("github"), conf, now, tz),
               source_state("slack", feeds.get("slack"), errors.get("slack"), conf, now, tz)]
    gh_ok = bool(feeds.get("github")) and feeds["github"].get("ok") is not False and not errors.get("github")

    open_ids = [i["id"] for i in items]
    snoozed_ids = [i["id"] for i in later]
    done, cleared = done_today(prev_state, open_ids, snoozed_ids, inbox, feeds, gh_ok, today, now, tz)

    state = {"date": today.isoformat(), "open": {}, "cleared": cleared, "sources_ok": {"github": gh_ok}}
    for i in items + later:
        first = (prev_open.get(i["id"]) or {}).get("first_seen") or i["since"] or iso(now)
        state["open"][i["id"]] = {"title": i["title"], "ref": i["ref"], "source": i["source"], "kind": i["kind"],
                                  "snoozed": is_snoozed(i), "first_seen": first}

    effort = sum(i["effort_min"] for i in items)
    due_today = sum(1 for i in items if i["due_today"])
    late = sum(1 for i in items if i["late"])
    view = {
        "built_at": iso(now),
        "today": today.isoformat(),
        "tz": getattr(tz, "key", None) or str(tz),
        "inbox": {"items": items, "snoozed": later, "done_today": done, "open": len(items), "due_today": due_today,
                  "late": late, "effort_min": effort, "effort": effort_label(effort), "bands": BAND_LABELS},
        "strip": {"need_you": len(items), "due_today": due_today, "late": late, "done_today": len(done),
                  "next_meeting": next_meeting(inbox, now, tz)},
        "sources": sources,
        "feeds": {},
        "inbox_config": {"cap": int(ib.get("cap") or 7), "home_count": int(ib.get("home_count") or 3)},
    }
    gh = feeds.get("github")
    if gh:
        view["feeds"]["github"] = {k: gh.get(k) or ([] if k != "login" else "") for k in
                                   ("login", "my_prs", "review_requests", "merged_recent")}

    if feeds.get("stats") is not None or errors.get("stats"):
        sources.append(source_state("stats", feeds.get("stats"), errors.get("stats"), conf, now, tz))
    stats = feeds.get("stats")
    view["stats"] = {k: stats.get(k) for k in STATS_KEYS if k in stats} if stats else None
    projects = data.get("projects") or []
    jobs = {p.get("id", ""): job_views(p, today, tz) for p in projects if p.get("jobs")}
    view["jobs"] = jobs
    for js in jobs.values():
        for j in js:
            add_parts(j, "job", conf)
    view["timeline"] = timeline_view(projects, jobs, today)
    view["project_timelines"] = {}
    for p in projects:
        tl = timeline_view(projects, jobs, today, p.get("id", ""))
        if tl["events"]:
            view["project_timelines"][p.get("id", "")] = tl
    view["pipeline"] = pipeline_view(gh, gh_ok)
    view["waiting"] = waiting_view(data.get("waiting_on"), today, tz)
    for it in items + later:
        add_parts(it, "inbox", conf)
    view["delivered"] = delivered_view(items, later, today, tz)
    view["projects"], view["waiting_on"], view["one_offs"] = linked_data(data, conf)
    view["unlinked"] = unlinked_mentions(view, data, inbox, conf)
    return view, state
