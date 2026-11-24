#!/usr/bin/env python3
"""Add or finish a one-off item in a project status data file.

  add_oneoff.py projects.json "Sign the two bank forms" --needs-me --due 2026-11-21 --note "HR portal"
  add_oneoff.py projects.json --done "bank forms"      (marks the first open item whose title contains the text,
                                                       and sets done_on to today so it shows under Wins today)

Then rebuild the page with build.py.
"""
import argparse, datetime, pathlib, sys

from datafile import locked_json

ap = argparse.ArgumentParser()
ap.add_argument("data"); ap.add_argument("title", nargs="?")
ap.add_argument("--due"); ap.add_argument("--note"); ap.add_argument("--ref")
ap.add_argument("--state", default="not started", choices=["not started", "in progress", "waiting", "blocked", "done"])
ap.add_argument("--pct", type=int); ap.add_argument("--needs-me", action="store_true"); ap.add_argument("--done")
a = ap.parse_args()
if not (a.done or a.title):
    ap.error("give a title or --done")
with locked_json(pathlib.Path(a.data)) as d:  # sys.exit inside the block leaves the file untouched
    items = d.setdefault("one_offs", [])
    if a.done:
        hit = next((o for o in items if a.done.lower() in o["title"].lower() and o.get("state") != "done"), None)
        if not hit: sys.exit(f"no open one-off matches {a.done!r}")
        hit["state"] = "done"; hit["done_on"] = datetime.date.today().isoformat(); print("done:", hit["title"])
    else:
        o = {"title": a.title, "state": a.state, "needs_me": a.needs_me}
        for k, v in (("due", a.due), ("note", a.note), ("ref", a.ref), ("progress_pct", a.pct)):
            if v is not None: o[k] = v
        items.append(o); print("added:", a.title)
