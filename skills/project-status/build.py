#!/usr/bin/env python3
"""Build a project status page from a data file.

Usage: build.py <projects.json> <out.html> [--config config.json]

projects.json:
  as_of        UTC timestamp string
  projects[]   id, name, priority, epic, status (On track | At risk | Blocked | Waiting | Wrapping up),
               progress_pct (0-100), progress_basis, next_milestone, deadline,
               needs_me[] {ask, ticket, due}, summary,
               breakdown[] {group, items[] {text, state (done | in progress | waiting | blocked | not started), owner, ref, date}},
               decisions[] {date, decision}, recent_progress[] {date, text}, links[] {label, url}
  waiting_on[] person, what, project_id, since, nudge_due, where
  one_offs[]   title (the only required field), state, needs_me (true/false), due, note, ref, progress_pct
               Small standalone items that belong to no project. Add one with add_oneoff.py.
Every field except a project's id and name is optional; the page skips what is missing.

config.json (optional, keeps anything specific to one person or company out of the template):
  title        page title
  tracker_url  prefix for ticket keys, for example https://example.atlassian.net/browse/
  github_org   org used to link refs like "repo 123"
  source_note  one sentence shown in the footer
  theme        {"light": {"--token": "value"}} overriding the template's color and font tokens.
               The page keeps one look in light and dark; add "dark" only if you want a separate dark palette.
"""
import argparse, json, pathlib

def block(sel, toks, extra=""):
    return sel + "{" + "".join(f"{k}:{v};" for k, v in toks.items()) + extra + "}"

ap = argparse.ArgumentParser()
ap.add_argument("data"); ap.add_argument("out"); ap.add_argument("--config")
a = ap.parse_args()
here = pathlib.Path(__file__).resolve().parent
d = json.loads(pathlib.Path(a.data).read_text())
cfg = json.loads(pathlib.Path(a.config).read_text()) if a.config else {}
theme = cfg.pop("theme", {})
d.pop("unsure", None)
d["config"] = {k: cfg[k] for k in ("title", "tracker_url", "github_org", "source_note") if k in cfg}
css = ""
if theme.get("light"):
    css += block(":root", theme["light"]) + "\n"
if theme.get("dark"):
    css += "@media (prefers-color-scheme: dark){" + block(':root:not([data-theme="light"])', theme["dark"], "color-scheme:dark") + "}\n"
    css += block(':root[data-theme="dark"]', theme["dark"], "color-scheme:dark") + "\n"
title = cfg.get("title", "Project Status").replace("<", "").replace("&", "and")
html = (here / "template.html").read_text()
html = html.replace("__TITLE__", title).replace("/*__THEME__*/", css)
html = html.replace("__DATA__", json.dumps(d, ensure_ascii=False).replace("<", "\\u003c"))
pathlib.Path(a.out).write_text(html)
print(f"{a.out}: {len(html)} bytes, {len(d['projects'])} projects, {len(d.get('waiting_on') or [])} waits")
