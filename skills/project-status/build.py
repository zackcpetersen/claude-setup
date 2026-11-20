#!/usr/bin/env python3
"""Build a project status page from a data file.

Usage: build.py <projects.json> <out.html> [--config config.json] [--home DIR] [--now ISO] [--no-state]

  --config    config.json (optional, explicit only).
  --home      folder holding inbox.json, feeds/ and state/ (usually ~/.claude/project-status). Explicit only:
              without it the page shows inbox items from projects.json alone and no state is written.
  --now       fixed clock, for tests.
  --no-state  read state/build.json but do not write it (try-it and test builds).

projects.json:
  as_of        UTC timestamp string
  projects[]   id, name, priority, epic, status (On track | At risk | Blocked | Waiting | Wrapping up),
               progress_pct (0-100), progress_basis, next_milestone, deadline,
               needs_me[] {ask, ticket, due, link, effort ("5m"), who_waits}, summary,
               breakdown[] {group, items[] {text, state (done | in progress | waiting | blocked | not started), owner, ref, date}},
               decisions[] {date, decision}, recent_progress[] {date, text}, links[] {label, url},
               next_milestone_date (YYYY-MM-DD, puts the milestone on the timeline),
               jobs[] {label, done, total, unit, per_day, eta, updated}: long jobs such as a backfill.
               Written by job.py, not by hand; the page works out percent, finish date and lateness.
  waiting_on[] person, what, project_id, since, nudge_due, where, link
  one_offs[]   title (the only required field), state, needs_me (true/false), due, note, ref, progress_pct
               Small standalone items that belong to no project. Add one with add_oneoff.py.
Every field except a project's id and name is optional; the page skips what is missing.
`link` on a needs_me or waiting_on row (a PR or Slack thread URL) lets the inbox merge it with the feeds.

config.json (optional, keeps anything specific to one person or company out of the template):
  title        page title
  tracker_url  prefix for ticket keys, for example https://example.atlassian.net/browse/
  github_org   org used to link refs like "repo 123"
  source_note  one sentence shown in the footer
  tz           IANA time zone for "today" (default: this machine's zone)
  inbox        cap, home_count, stale_days, slack_url, effort_defaults and the feed settings (see derive.DEFAULTS)
  feeds        every_minutes, hours, days: the status-feeds schedule, used to tell when a feed is stale
  links        {"patterns": [{"match": "<regex with one group>", "url": "<base>{1}"}]}: link bases for other keys
  stats        settings for ~/bin/eng-stats (it writes feeds/stats.json, which the #stats page reads)
  theme        {"light": {"--token": "value"}} overriding the page's color and font tokens (page.css :root).
               The page keeps one look in light and dark; add "dark" only if you want a separate dark palette.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive  # noqa: E402


def block(sel, toks, extra=""):
    return sel + "{" + "".join(f"{k}:{v};" for k, v in toks.items()) + extra + "}"


def theme_css(theme):
    css = ""
    if theme.get("light"):
        css += block(":root", theme["light"]) + "\n"
    if theme.get("dark"):
        css += "@media (prefers-color-scheme: dark){" + block(':root:not([data-theme="light"])', theme["dark"], "color-scheme:dark") + "}\n"
        css += block(':root[data-theme="dark"]', theme["dark"], "color-scheme:dark") + "\n"
    return css


def read_json(path, label, errors):
    """Parsed JSON, or None when the file is missing. A bad file is noted in errors and skipped."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as e:
        msg = f"{path.name} could not be read: {str(e).splitlines()[0][:120]}"
        print(f"warning: {msg}", file=sys.stderr)
        errors[label] = msg
        return None


def render(page, title):
    html = (HERE / "template.html").read_text()
    for marker, value in (("__TITLE__", title), ("/*__CSS__*/", (HERE / "page.css").read_text()),
                          ("/*__THEME__*/", page.pop("_theme_css")), ("/*__JS__*/", (HERE / "page.js").read_text()),
                          ("__DATA__", json.dumps(page, ensure_ascii=False).replace("<", "\\u003c"))):
        html = html.replace(marker, value, 1)
    return html


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--config")
    ap.add_argument("--home")
    ap.add_argument("--now")
    ap.add_argument("--no-state", action="store_true")
    a = ap.parse_args(argv)

    now = derive.parse_time(a.now) if a.now else datetime.now(timezone.utc)
    if now is None:
        ap.error("--now takes an ISO time")
    d = json.loads(pathlib.Path(a.data).read_text())
    cfg = json.loads(pathlib.Path(a.config).read_text()) if a.config else {}
    theme = cfg.pop("theme", {}) or {}
    d.pop("unsure", None)

    errors, inbox, feeds, prev = {}, None, {"github": None, "slack": None, "stats": None}, {}
    home = pathlib.Path(a.home).expanduser() if a.home else None
    if home:
        inbox = read_json(home / "inbox.json", "session", errors)
        for name in feeds:
            feeds[name] = read_json(home / "feeds" / f"{name}.json", name, errors)
        prev = read_json(home / "state" / "build.json", "state", {}) or {}

    view, state = derive.build_view(d, cfg, inbox, feeds, prev, now, errors)
    if home and not a.no_state:
        sdir = home / "state"
        sdir.mkdir(parents=True, exist_ok=True)
        tmp = sdir / "build.json.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
        tmp.replace(sdir / "build.json")

    page = {k: d[k] for k in ("as_of",) if k in d}
    page.setdefault("projects", [])
    page["config"] = {k: cfg[k] for k in ("title", "tracker_url", "github_org", "source_note") if k in cfg}
    page["config"]["inbox"] = view.pop("inbox_config")
    page.update(view)
    page["_theme_css"] = theme_css(theme)
    title = str(cfg.get("title", "Project Status")).replace("<", "").replace(">", "").replace("&", "and")
    html = render(page, title)
    pathlib.Path(a.out).write_text(html)
    unlinked = view.get("unlinked") or []
    for u in unlinked[:20]:
        print(f"warning: unlinked mention {u['text']} at {u['where']} ({u['why']})", file=sys.stderr)
    if len(unlinked) > 20:
        print(f"warning: and {len(unlinked) - 20} more unlinked mentions", file=sys.stderr)
    stats_state = next((x["state"] for x in view["sources"] if x["name"] == "stats"), "missing")
    print(f"{a.out}: {len(html)} bytes, {len(page['projects'])} projects, {len(d.get('waiting_on') or [])} waits, "
          f"{view['inbox']['open']} inbox items, stats {stats_state}, {len(unlinked)} unlinked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
