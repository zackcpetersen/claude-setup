"""Turn project data, the session inbox and the feed files into the page's inbox view.

Pure functions only: no file access, no clock. build.py loads the files and passes `now`.
Every rule about inbox items lives here (refs, ids, effort, bands, order, dedupe, snooze,
stale, done today, source freshness) so the page and the scripts stay simple.
"""
import copy
import hashlib
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
    },
    "feeds": {"every_minutes": 15, "hours": "08:00-18:00", "days": "Mon-Fri"},
}

EFFORT = {"merge": 2, "send-draft": 2, "approve-agent": 2, "slack": 5, "nudge": 5, "confirm": 5, "todo": 5,
          "fix-ci": 15, "reply-review": 15, "conflict": 15, "ask": 15, "oneoff": 15}
PR_FIX_KINDS = ("conflict", "fix-ci", "reply-review")
SOURCE_RANK = {"session": 0, "projects": 1, "github": 2, "slack": 3}
SCRIPT_SOURCES = ("github", "slack")
BAND_LABELS = {1: "Late or today", 2: "Waiting on you", 3: "Quick wins", 4: "Your PR fixes", 5: "Everything else"}
SOURCE_LABELS = {"projects": "Projects", "session": "Session", "github": "GitHub", "slack": "Slack"}
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


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
                       who_waits=n.get("who_waits") or "", source="projects", ticket=n.get("ticket") or "")
            it["id"] = it["ref"] or f"proj:{pid}:{key}"
            out.append(it)
    for o in data.get("one_offs") or []:
        if not o.get("needs_me") or str(o.get("state", "")).lower() == "done":
            continue
        link = o.get("ref") if str(o.get("ref") or "").startswith("https://") else ""
        it = _item(kind="oneoff", title=o.get("title") or "", why=o.get("note") or "", link=link,
                   due=o.get("due") or None, source="projects")
        it["id"] = it["ref"] or "oneoff:" + sha(o.get("title") or "")
        out.append(it)
    for w in data.get("waiting_on") or []:
        nd = parse_day(w.get("nudge_due"))
        if not nd or nd > today:
            continue
        person = w.get("person") or "someone"
        it = _item(kind="nudge", title=f"Nudge {person}: {w.get('what') or ''}".strip().rstrip(":"),
                   why=w.get("where") or "", link=w.get("link") or "", project_id=w.get("project_id") or "",
                   since=w.get("since") or None, due=w.get("nudge_due"), source="projects")
        it["id"] = it["ref"] or f"nudge:{w.get('project_id') or ''}:{person}"
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


def pr_kind(pr):
    """The one inbox item for one of my open PRs, as (kind, why), or None. Never infers from UNKNOWN or null."""
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
    if (pr.get("review_decision") == "APPROVED" and ci in ("SUCCESS", None)
            and pr.get("merge_state") not in ("BLOCKED", "DIRTY", "BEHIND")):
        return "merge", "Approved, merge check pending" if pr.get("mergeable") == "UNKNOWN" else "Approved and green"
    return None


PR_VERB = {"conflict": "Fix conflict", "fix-ci": "Fix CI", "reply-review": "Reply to review", "merge": "Merge"}


def github_items(feed, overrides):
    out = []
    if not feed:
        return out
    for pr in feed.get("my_prs") or []:
        got = pr_kind(pr)
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
        link = f"{slack_url}{ch}/p{ts.replace('.', '')}" if slack_url and ch and ts else ""
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
            out.append(g[0])
            continue
        top = dict(g[0])
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
    st["as_of"] = gen.astimezone(tz).strftime("%H:%M") if gen else None
    st["last_ok_at"] = feed.get("last_ok_at")
    if feed.get("ok") is False:
        st.update(state="failing", error=feed.get("error") or "failed")
        return st
    st["state"] = "ok"
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
    if prev.get("date") == today.isoformat() and (prev.get("sources_ok") or {}).get("github") and gh_ok_now:
        for pid, p in (prev.get("open") or {}).items():
            if pid in open_ids or pid in seen or not pid.startswith("gh:") or p.get("snoozed"):
                continue
            if p.get("source") != "github":  # projects and session items are never counted by absence
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
    feeds: {"github": dict or None, "slack": dict or None}. prev_state: state/build.json or {}.
    now: aware datetime. errors: {"session"|"github"|"slack": "parse error text"} for files that failed to load.
    Returns (view, state).
    """
    conf = settings(cfg)
    errors = errors or {}
    feeds = feeds or {}
    prev_state = prev_state or {}
    tz = local_tz(conf.get("tz"))
    today = now.astimezone(tz).date()
    ib = conf["inbox"]
    overrides = ib.get("effort_defaults") or {}

    shown, snoozed = session_items(inbox, today)
    raw = shown + snoozed + project_items(data, today)
    raw += github_items(feeds.get("github"), overrides)
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
        state["open"][i["id"]] = {"title": i["title"], "ref": i["ref"], "source": i["source"],
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
    return view, state
