#!/usr/bin/env python3
"""Write the session's inbox items for the status page (inbox.json). The session never hand-edits that file.

  inbox.py [--home DIR] add --kind K --title T [--why W] [--link URL] [--ref R] [--project ID] [--due D]
                            [--effort 5m] [--who NAME] [--since ISO] [--id ID] [--origin session|board]
  inbox.py [--home DIR] done <id-or-title-text>
  inbox.py [--home DIR] snooze <id-or-title-text> --until YYYY-MM-DD      (inbox.json items only)
  inbox.py [--home DIR] sync --origin board --file items.json
  inbox.py [--home DIR] meeting --title T --at ISO   |   meeting --clear
  inbox.py [--home DIR] list

--home defaults to ~/.claude/project-status. Kinds: approve-agent, send-draft, confirm, todo, ask.
An item's id is its --ref when given, else --id, else a slug of the title. Adding an id that exists
updates only the fields given; `since` and `snooze_until` are kept, and a done item opens again.
`sync` upserts every item in the file (a JSON list of objects with the same field names as `add`,
long or short: project or project_id, who or who_waits, effort or effort_min) and marks every open
item of that origin missing from the file as done. Done items are deleted 2 days after done_at.
Then rebuild the page with build.py.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive import canonical_ref  # noqa: E402

KINDS = ("approve-agent", "send-draft", "confirm", "todo", "ask")
FIELDS = ("kind", "title", "why", "link", "ref", "project_id", "since", "due", "effort_min", "who_waits", "origin")
ALIASES = {"project": "project_id", "who": "who_waits", "effort": "effort_min"}
KEEP_DONE = timedelta(days=2)
NOW = lambda: datetime.now(timezone.utc)


class Fail(Exception):
    pass


def stamp(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text):
    if not text:
        return None
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_effort(value):
    if value is None or value == "":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    m = re.fullmatch(r"\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?\s*", str(value).lower())
    if str(value).strip().isdigit():
        return int(str(value).strip())
    if not m or not (m.group(1) or m.group(2)):
        raise Fail(f"cannot read effort {value!r}; use 5m, 1h or 1h 10m")
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def slug_id(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return (s or "item") + "-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]


def load(path):
    if not path.exists():
        return {"version": 1, "updated_at": None, "next_meeting": None, "items": []}
    try:
        d = json.loads(path.read_text())
    except ValueError as e:
        raise Fail(f"{path} is not valid JSON ({e}); fix or move it, then retry")
    d.setdefault("version", 1)
    d.setdefault("items", [])
    return d


def save(path, d, now):
    keep = []
    for it in d["items"]:
        done = parse_time(it.get("done_at"))
        if done and now - done > KEEP_DONE:
            continue
        keep.append(it)
    d["items"] = keep
    d["updated_at"] = stamp(now)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, path)


def normalize(raw):
    """One item dict from add args or a sync file entry, with long field names only."""
    out = {}
    for k, v in raw.items():
        k = ALIASES.get(k, k)
        if k in FIELDS or k in ("id", "snooze_until"):
            out[k] = v
    if out.get("ref"):
        out["ref"] = canonical_ref(out["ref"])
    if "effort_min" in out:
        out["effort_min"] = parse_effort(out["effort_min"])
    if out.get("kind") is not None and out["kind"] not in KINDS:
        raise Fail(f"kind {out['kind']!r} is not one of: {', '.join(KINDS)}")
    return {k: v for k, v in out.items() if v is not None}


def upsert(d, item, now):
    """Add or update by id. Fields not given keep their stored value; since and snooze_until survive."""
    item_id = item.get("ref") or item.get("id") or (slug_id(item["title"]) if item.get("title") else None)
    if not item_id:
        raise Fail("an item needs --ref, --id or --title")
    item["id"] = item_id
    cur = next((i for i in d["items"] if i.get("id") == item_id), None)
    if cur is None:
        if not item.get("title"):
            raise Fail(f"new item {item_id!r} needs a title")
        if not item.get("kind"):
            raise Fail(f"new item {item_id!r} needs a kind")
        cur = {"id": item_id, "origin": "session", "kind": item["kind"], "title": item["title"], "why": "",
               "link": "", "ref": "", "project_id": "", "since": stamp(now), "due": None, "effort_min": None,
               "who_waits": "", "snooze_until": None, "done_at": None}
        d["items"].append(cur)
    for k, v in item.items():
        if k == "snooze_until" and cur.get("snooze_until"):
            continue
        cur[k] = v
    cur["done_at"] = None
    return cur


def find(d, text):
    """Exact id first, then the first open item whose title holds the text (case-insensitive)."""
    hit = next((i for i in d["items"] if i.get("id") == text), None)
    if hit:
        return hit
    low = text.lower()
    return next((i for i in d["items"] if not i.get("done_at") and low in (i.get("title") or "").lower()), None)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inbox.py", description=__doc__.split("\n")[0])
    ap.add_argument("--home", default="~/.claude/project-status")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--title", required=True)
    for f in ("why", "link", "ref", "project", "due", "effort", "who", "since", "id"):
        a.add_argument("--" + f)
    a.add_argument("--origin", choices=("session", "board"), default=None)
    dn = sub.add_parser("done")
    dn.add_argument("target")
    sn = sub.add_parser("snooze")
    sn.add_argument("target")
    sn.add_argument("--until", required=True)
    sy = sub.add_parser("sync")
    sy.add_argument("--origin", required=True, choices=("board",))
    sy.add_argument("--file", required=True)
    mt = sub.add_parser("meeting")
    mt.add_argument("--title")
    mt.add_argument("--at")
    mt.add_argument("--clear", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args(argv)

    path = Path(os.path.expanduser(args.home)) / "inbox.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(path.with_name("inbox.json.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # one writer at a time: the board sync and a landed event can overlap
    try:
        return run(args, path)
    finally:
        lock.close()


def run(args, path):
    now = NOW()
    try:
        d = load(path)
        if args.cmd == "add":
            raw = {"kind": args.kind, "title": args.title, "why": args.why, "link": args.link, "ref": args.ref,
                   "project": args.project, "due": args.due, "effort": args.effort, "who": args.who,
                   "since": args.since, "id": args.id, "origin": args.origin}
            it = upsert(d, normalize(raw), now)
            save(path, d, now)
            print("saved:", it["id"])
        elif args.cmd == "done":
            it = find(d, args.target)
            if not it:
                raise Fail(f"no inbox item matches {args.target!r}")
            it["done_at"] = stamp(now)
            save(path, d, now)
            print("done:", it["id"])
        elif args.cmd == "snooze":
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", args.until):
                raise Fail("--until takes YYYY-MM-DD")
            it = find(d, args.target)
            if not it:
                raise Fail(f"no inbox.json item matches {args.target!r} (only session items can be snoozed)")
            it["snooze_until"] = args.until
            save(path, d, now)
            print("snoozed:", it["id"], "until", args.until)
        elif args.cmd == "sync":
            try:
                entries = json.loads(Path(os.path.expanduser(args.file)).read_text())
            except (OSError, ValueError) as e:
                raise Fail(f"cannot read {args.file}: {e}")
            if not isinstance(entries, list):
                raise Fail(f"{args.file} must hold a JSON list of items")
            items = [normalize(dict(e, origin=args.origin)) for e in entries]
            seen = {upsert(d, it, now)["id"] for it in items}
            closed = 0
            for it in d["items"]:
                if it.get("origin") == args.origin and not it.get("done_at") and it["id"] not in seen:
                    it["done_at"] = stamp(now)
                    closed += 1
            save(path, d, now)
            print(f"synced: {len(seen)} open, {closed} marked done")
        elif args.cmd == "meeting":
            if args.clear:
                d["next_meeting"] = None
            else:
                if not args.title or not parse_time(args.at or ""):
                    raise Fail("meeting needs --title and an ISO --at with a zone, or --clear")
                d["next_meeting"] = {"title": args.title, "at": args.at}
            save(path, d, now)
            print("meeting:", "cleared" if args.clear else f"{args.title} at {args.at}")
        else:
            for it in d["items"]:
                if not it.get("done_at"):
                    print(" | ".join([it["id"], it.get("kind") or "", it.get("title") or "", it.get("due") or ""]))
    except Fail as e:
        print("inbox.py:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
