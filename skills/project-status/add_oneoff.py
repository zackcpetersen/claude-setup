#!/usr/bin/env python3
"""Add or finish a one-off item in a project status data file.

  add_oneoff.py projects.json "Sign the two bank forms" --needs-me --due 2026-11-21 --note "HR portal"
  add_oneoff.py projects.json --done "bank forms"      (marks the first open item whose title contains the text)

Then rebuild the page with build.py.
"""
import argparse, json, pathlib, sys

ap = argparse.ArgumentParser()
ap.add_argument("data"); ap.add_argument("title", nargs="?")
ap.add_argument("--due"); ap.add_argument("--note"); ap.add_argument("--ref")
ap.add_argument("--state", default="not started", choices=["not started", "in progress", "waiting", "blocked", "done"])
ap.add_argument("--pct", type=int); ap.add_argument("--needs-me", action="store_true"); ap.add_argument("--done")
a = ap.parse_args()
f = pathlib.Path(a.data); d = json.loads(f.read_text()); items = d.setdefault("one_offs", [])
if a.done:
    hit = next((o for o in items if a.done.lower() in o["title"].lower() and o.get("state") != "done"), None)
    if not hit: sys.exit(f"no open one-off matches {a.done!r}")
    hit["state"] = "done"; print("done:", hit["title"])
elif a.title:
    o = {"title": a.title, "state": a.state, "needs_me": a.needs_me}
    for k, v in (("due", a.due), ("note", a.note), ("ref", a.ref), ("progress_pct", a.pct)):
        if v is not None: o[k] = v
    items.append(o); print("added:", a.title)
else:
    ap.error("give a title or --done")
f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
