#!/usr/bin/env python3
"""Apply board events (from ~/bin/board-event) to a project status data file.

  apply_events.py projects.json [--events-dir DIR] [--config config.json] [--now ISO] [--dry-run]

Reads the events after the file's top-level `events_cursor` (no cursor: the start of today's log file), applies
the kinds that need no judgment, sets `as_of` and moves `events_cursor` to the last event read, in one locked,
atomic write. Prints `applied N, skipped N, unplaced N`, then one `unplaced <id> <kind> <key>: <text>` line each.
Unplaced events (no matching project, a `failed`, a `cleared` that matched nothing) are for the publisher to relay
or place by hand; the cursor still moves past them. Every edit is dated with the event's own `day`, and every edit
checks for an existing row first, so a replay never adds a line twice.

The events folder is --events-dir, else BOARD_EVENTS_DIR, else ~/.claude/board-events. A missing folder or an
empty log only sets `as_of`. The applier never touches progress_pct, status, breakdown, summary or next_milestone.
"""
import argparse
import fcntl
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import job
from datafile import NoWrite, locked_json
from derive import canonical_ref

ID_RE = re.compile(r"^\d{8}T\d{6}Z-\d{4}$")
TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
PROGRESS_KINDS = {"merged", "deployed", "run-finished", "note"}
NO_CHANGE_KINDS = {"run-started", "goal-tick", "draft-created", "draft-sent"}


# ---------- reading the log ----------

def events_dir(given):
    return Path(given or os.environ.get("BOARD_EVENTS_DIR") or Path.home() / ".claude" / "board-events")


def day_files(folder, start):
    for p in sorted(folder.glob("*.jsonl")):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d >= start:
            yield p


def read_events(folder, start):
    """Every parseable event in day files from `start` on, in id order. Torn lines are skipped with a warning."""
    if not folder.is_dir():
        return []
    rows = []
    with open(folder / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        for path in day_files(folder, start):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    ev = None
                if not isinstance(ev, dict) or not ID_RE.match(str(ev.get("id") or "")):
                    print(f"warning: skipped unreadable line {path.name}:{n}", file=sys.stderr)
                    continue
                rows.append(ev)
    return sorted(rows, key=lambda e: e["id"])


def new_events(folder, cursor, today):
    if cursor and ID_RE.match(cursor):
        # ids are UTC and files are local days: start one day before the cursor's UTC date
        start = date(int(cursor[:4]), int(cursor[4:6]), int(cursor[6:8])) - timedelta(days=1)
        return [e for e in read_events(folder, start) if e["id"] > cursor]
    return [e for e in read_events(folder, today) if e.get("day", today.isoformat()) == today.isoformat()]


# ---------- matching ----------

def ev_day(ev):
    return ev.get("day") or str(ev.get("ts") or "")[:10]


def ev_link(ev):
    links = ev.get("links") or []
    return links[0] if links else ""


def same_link(a, b):
    return bool(a) and bool(b) and canonical_ref(a) == canonical_ref(b)


def find_project(data, ev):
    """First match wins: project field, key as id, key as epic / breakdown ref / needs_me ticket."""
    projects = data.get("projects") or []
    want, key = ev.get("project"), ev.get("key")
    for test in (
        lambda p: want and p.get("id") == want,
        lambda p: key and p.get("id") == key,
        lambda p: key and (p.get("epic") == key
                           or any(i.get("ref") == key for g in p.get("breakdown") or [] for i in g.get("items") or [])
                           or any(n.get("ticket") == key for n in p.get("needs_me") or [])),
    ):
        hit = next((p for p in projects if test(p)), None)
        if hit is not None:
            return hit
    return None


def find_oneoff(data, ev):
    refs = {r for r in (ev.get("key"), ev.get("ref")) if r}
    for o in data.get("one_offs") or []:
        r = o.get("ref")
        if r and (r in refs or any(same_link(r, x) for x in refs) or same_link(r, ev_link(ev))):
            return o
    return None


def clear_target(ev, by_id):
    """(link, text) a cleared event points at: its own link, else the cleared event's link and text."""
    target = by_id.get((ev.get("fields") or {}).get("clears")) or {}
    return ev_link(ev) or ev_link(target), target.get("text") or ""


def is_cleared_later(ev, later, by_id):
    for c in later:
        if c.get("kind") != "cleared":
            continue
        if (c.get("fields") or {}).get("clears") == ev["id"]:
            return True
        link, text = clear_target(c, by_id)
        if same_link(link, ev_link(ev)) or (text and text == ev.get("text")):
            return True
    return False


# ---------- edits ----------

def add_progress(project, day, text):
    rows = project.setdefault("recent_progress", [])
    if any(r.get("date") == day and r.get("text") == text for r in rows):
        return False
    rows.append({"date": day, "text": text})
    return True


def add_decision(project, day, text):
    rows = project.setdefault("decisions", [])
    if any(r.get("date") == day and r.get("decision") == text for r in rows):
        return False
    rows.append({"date": day, "decision": text})
    return True


def plus_business_days(day, n):
    d = date.fromisoformat(day)
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d.isoformat()


def add_needs_me(project, ev):
    rows = project.setdefault("needs_me", [])
    link, text, f = ev_link(ev), ev.get("text"), ev.get("fields") or {}
    if any(same_link(r.get("link"), link) or r.get("ask") == text for r in rows):
        return False
    row = {"ask": text}
    if link:
        row["link"] = link
    if TICKET_RE.match(str(ev.get("key") or "")):
        row["ticket"] = ev["key"]
    for k in ("due", "effort"):
        if f.get(k) is not None:
            row[k] = f[k]
    rows.append(row)
    return True


def add_waiting(data, project, ev):
    rows = data.setdefault("waiting_on", [])
    link, text, f = ev_link(ev), ev.get("text"), ev.get("fields") or {}
    if any(same_link(r.get("link"), link) or r.get("what") == text for r in rows):
        return False
    day = ev_day(ev)
    row = {"person": f.get("who") or "", "what": text, "project_id": project.get("id"), "since": day,
           "nudge_due": f.get("nudge_due") or plus_business_days(day, 3)}
    if link:
        row["link"] = link
    rows.append(row)
    return True


def clear(data, ev, by_id):
    link, text = clear_target(ev, by_id)
    hit = False
    for p in data.get("projects") or []:
        keep = [r for r in p.get("needs_me") or [] if not (same_link(r.get("link"), link) or (text and r.get("ask") == text))]
        if len(keep) != len(p.get("needs_me") or []):
            p["needs_me"], hit = keep, True
    keep = [r for r in data.get("waiting_on") or [] if not (same_link(r.get("link"), link) or (text and r.get("what") == text))]
    if len(keep) != len(data.get("waiting_on") or []):
        data["waiting_on"], hit = keep, True
    o = find_oneoff(data, ev) or (find_oneoff(data, by_id[ev["fields"]["clears"]])
                                  if (ev.get("fields") or {}).get("clears") in by_id else None)
    if o is not None and o.get("state") != "done":
        o["state"], o["done_on"], hit = "done", ev_day(ev), True
    return hit, hit or o is not None


def apply_one(data, ev, later, by_id, tz):
    """'applied', 'skipped' or 'unplaced'."""
    kind = ev.get("kind")
    f = ev.get("fields") or {}
    if kind == "failed":
        return "unplaced"
    if kind == "cleared":
        changed, matched = clear(data, ev, by_id)
        return "applied" if changed else ("skipped" if matched else "unplaced")
    if kind in NO_CHANGE_KINDS and not (kind == "run-started" and f.get("job")):
        return "skipped"
    project = find_project(data, ev)
    if project is None:
        return "unplaced"
    day, text = ev_day(ev), ev.get("text") or ""
    when = job.parse_now(ev.get("ts")) if ev.get("ts") else None
    if kind in PROGRESS_KINDS:
        changed = add_progress(project, day, text)
    elif kind == "decision":
        changed = add_progress(project, day, text) | add_decision(project, day, text)
    elif kind in ("job-progress", "run-started"):
        if not f.get("job"):
            return "unplaced"
        job.set_job(project, str(f["job"]), f, when or datetime.now(timezone.utc))
        changed = True
    elif kind == "job-done":
        if not f.get("job"):
            return "unplaced"
        changed = job.finish_job(project, str(f["job"]), when, tz, day=day) is not None
    elif kind in ("needs-you", "waiting-on"):
        if is_cleared_later(ev, later, by_id):
            return "skipped"
        changed = add_needs_me(project, ev) if kind == "needs-you" else add_waiting(data, project, ev)
    else:
        return "unplaced"
    return "applied" if changed else "skipped"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apply board events to a project status data file.")
    ap.add_argument("data")
    ap.add_argument("--events-dir", help="event log folder (default: BOARD_EVENTS_DIR or ~/.claude/board-events)")
    ap.add_argument("--config", help="config.json for tz (default: config.json next to the data file)")
    ap.add_argument("--now", help="fixed clock (ISO), for tests")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    a = ap.parse_args(argv)

    now = job.parse_now(a.now)
    tz = job.config_tz(a.data, a.config)
    today = now.astimezone().date()  # the machine's local day, which is how board-event names its day files
    folder = events_dir(a.events_dir)
    counts, unplaced = {"applied": 0, "skipped": 0, "unplaced": 0}, []
    with locked_json(Path(a.data)) as data:
        events = new_events(folder, data.get("events_cursor"), today)
        # a cleared event may point (fields.clears) at an event before the cursor: index the whole folder
        by_id = {e["id"]: e for e in (read_events(folder, date.min)
                                      if any(e.get("kind") == "cleared" for e in events) else events)}
        for i, ev in enumerate(events):
            result = apply_one(data, ev, events[i + 1:], by_id, tz)
            counts[result] += 1
            if result == "unplaced":
                unplaced.append(ev)
        if events:
            data["events_cursor"] = events[-1]["id"]
        data["as_of"] = job.stamp(now)
        print(f"applied {counts['applied']}, skipped {counts['skipped']}, unplaced {counts['unplaced']}"
              + (" (dry run, nothing written)" if a.dry_run else ""))
        for ev in unplaced:
            print(f"unplaced {ev['id']} {ev.get('kind')} {ev.get('key')}: {ev.get('text')}")
        if a.dry_run:
            raise NoWrite
    return 0


if __name__ == "__main__":
    sys.exit(main())
