---
name: project-status
description: Use when the user asks for a visual status of their projects, a project dashboard or status page, to refresh or republish it, or to add, change or finish a one-off item on it.
---

# Project status

A visual status page, published as a private Artifact. It reads as a dashboard: a left nav rail (a bottom tab bar on phones), a light grid of tiles, bars and sparklines instead of paragraphs. Detail lives on each page.

Pages. The rail holds Home, Inbox, Projects, PRs, Stats and More; More opens a sheet with the rest:

- **Home** (`#home`): a header (date, Me/Team and 30d/90d toggles, Focus), the today strip (need you, due today, late, done today, next meeting), four KPI tiles with sparklines and a throughput tile (when stats exist), project rows with progress bars, a "Next 3 weeks" timeline, and side panels: Needs you (with an effort bar), the PR pipeline and Waiting on. Focus (button or the `f` key) shows only the header, the strip and Needs you.
- **Inbox** (`#inbox`, `#inbox/<hid>` highlights one row): every open item in bands (late or today, waiting on you, quick wins, your PR fixes, everything else), the first `inbox.cap` shown and the rest folded, then snoozed and done today. Rows new since you last looked get a small dot.
- **Projects** (`#projects`): every project row, then the one-offs.
- **PRs** (`#prs`): the PR pipeline (draft, in review, approved, merged this week) and the reviews asked of you. Needs the GitHub feed.
- **Stats** (`#stats`, also `#stats/<me|team>/<30|90>`): KPI tiles, throughput, turnaround (median with a p90 tick) and the split by repo group. Needs `~/bin/eng-stats`.
- **One page per project** (`#p-<id>`): the hero, long jobs with progress bars and finish dates, the project's dates, what is needed from the user, where it stands, the full breakdown, people it waits on (aging bars), recent decisions and progress, links.
- **Waiting on others** (`#waiting`): everything owed by someone else, grouped by person, each with an aging bar and a tick at the nudge date.
- **Delivered, not confirmed** (`#delivered`): a countdown bar per delivery until its confirm-by date.
- **Other items** (`#other`): small standalone items that belong to no project.

Old links keep working: `#overview` opens Home, `#people` opens Waiting on others, `#oneoffs` opens Other items. Color rule: the accent is for progress and done; coral only for something late; counts are neutral; no color stands for a person. Every ticket key, PR, thread or page the page names is a link to its source (see "Links").

Nothing in this skill names a company, person or project. Those come from the data and config files.

## Files

| File | What it is |
|---|---|
| `template.html` | The page shell. `build.py` inlines `page.css`, `page.js`, the theme and the data into it, so the published page is one file |
| `page.css`, `page.js` | All styles and all page code. Neutral colors, no names or links baked in |
| `build.py` | Turns a data file (and optional config and home folder) into the page. The data format is in its docstring |
| `derive.py` | Every rule the page shows: inbox items, dedupe, bands, freshness, plus job finish dates, the timeline, the PR pipeline, waiting and delivery bars, and mention links |
| `inbox.py` | The only way the session writes `inbox.json` |
| `add_oneoff.py` | Adds or finishes a one-off in the data file |
| `job.py` | Records progress on a long job (a backfill, a big export) in the data file |
| `config.example.json` | Starter config: title, tracker and GitHub link bases, footer note, time zone, inbox and feed settings, color overrides |
| `sample-data.json`, `sample-home/` | Made-up data, inbox and feeds to try the page with |
| `tests/` | `unittest` tests: `python3 -m unittest discover -s skills/project-status/tests` |
| `~/bin/status-feeds` | From `bin/` in this repo. Writes the GitHub and Slack feed files on a schedule, no model in the loop |
| `~/bin/eng-stats` | From `bin/` in this repo. Caches the org's PRs and writes `feeds/stats.json` (aggregates for me and my team only) once a day |

Per-machine files live outside the repo, in `~/.claude/project-status/`:

- `config.json`: copied from `config.example.json` and filled in. Also holds `artifact_url` once the page is published.
- `projects.json`: the current data.
- `inbox.json`: session-owned inbox items, written only by `inbox.py`.
- `feeds/github.json`, `feeds/slack.json`: written only by `status-feeds`. `feeds/stats.json` and `cache/`: written only by `eng-stats`.
- `state/build.json`: written only by `build.py` (first-seen times and what cleared today).

## Setup (once per machine)

1. `mkdir -p ~/.claude/project-status`
2. `cp ~/.claude/skills/project-status/config.example.json ~/.claude/project-status/config.json` and fill in `title`, `tracker_url` (the prefix a ticket key is added to), `github_org` and `source_note`. Delete a line you do not need.
3. Colors: `theme.light` and `theme.dark` override the page's tokens (the full list is the `:root` block at the top of `page.css`). The groups: surfaces (`--canvas`, `--card`, `--line`, `--track`), ink (`--text`, `--strong`, `--muted`), the rail (`--rail`, `--rail-ink`, `--rail-on`), progress (`--accent`, `--accent-ink`), charts (`--chart-1`, `--chart-2`, `--chart-grid`, `--prog`), late (`--alert`, `--alert-ink`, `--alert-bg`), `--link` and `--font`. The repo ships a neutral palette in light and dark. A brand palette (from the user's design system) goes only in this local config, in both `theme.light` and `theme.dark`, never in the repo. Keep text pairs at 4.5:1 contrast.
4. Try it with the sample: `python3 ~/.claude/skills/project-status/build.py ~/.claude/skills/project-status/sample-data.json <scratchpad>/project-status.html --config ~/.claude/project-status/config.json --home ~/.claude/skills/project-status/sample-home --no-state --now 2026-01-12T18:00:00Z`, then publish that file with the Artifact tool to see the look.
5. Feeds (optional): set `tz` in `config.json` (an IANA name), then `~/bin/status-feeds doctor`, then `~/bin/status-feeds run --force`, then install the schedule with the commands `~/bin/status-feeds schedule --print launchd` prints (Linux: `--print cron`, add it with `crontab -e`). Install it only with the user's yes. Set `inbox.github_orgs` when your PRs live in more than one org, and `inbox.slack_url` (for example `https://<workspace>.slack.com/archives/`) so Slack items link to their thread. A PR only shows as "Merge" once its checks have passed; list repos that have no checks at all in `inbox.no_ci_repos` (`owner/repo`) so their approved PRs can show as ready too.
6. Stats (optional): set `stats.org` (or rely on `github_org`) and `stats.team_slug` (the GitHub team that is "my team"; `stats.team_members` is the fallback list), then `~/bin/eng-stats doctor`, then `~/bin/eng-stats run` (the first fill takes about 25 minutes and about 150 of the 5,000 hourly GraphQL points), then install the daily schedule `~/bin/eng-stats schedule --print launchd` prints (Linux: `--print cron`). Install it only with the user's yes. Optional keys: `repos_include`, `repos_skip`, `repo_groups`, `bots`, `business_hours_clock`.
7. First real build: follow "Refresh" below. After the first publish, save the Artifact link as `artifact_url` in `config.json` so later sessions update the same page.

If `~/.claude/project-status/config.json` is missing, do steps 1 and 2 with the user before anything else.

## Refresh

1. **Gather** the data into `~/.claude/project-status/projects.json`, in the format from `build.py`'s docstring. Dispatch one read-only agent for this (pass `model`); it writes only that file. Sources, in order: the user's project notes (for the `board` skill, the `Projects data source` line in `~/.claude/config/board.md` (older installs: `### Work board` in `~/.claude/CLAUDE.md`), plus today's board row), then the tracker and GitHub only for gaps. Rules for the agent:
   - `needs_me` holds only what the user must do or decide by hand. What waits on someone else goes in `waiting_on`. What an agent can do alone goes in neither.
   - `progress_pct` comes from real milestones or tickets, and `progress_basis` says how in one sentence. Never invent precision.
   - Keep `one_offs` and every project's `jobs` already in the file. They are the user's own list and `job.py`'s.
   - Set `next_milestone_date` (`YYYY-MM-DD`) when the next milestone has a date, so it shows on the timeline.
   - Every item carries a link to its source when it names one: `link` on asks and waits, `ref` or `links[]` for tickets, PRs, Notion pages, Slack threads, runs and docs.
   - Keep `link`, `effort` and `who_waits` fields when present, and set `needs_me[].link` and `waiting_on[].link` whenever the source line has a URL (a Slack thread, a PR), so items merge with the feeds instead of showing twice.
   - Plain English, short sentences. Leave out finished projects.
   - Skip the Projects row named by the `Loose ends` line in `~/.claude/config/tidy.md` (older installs: `### Tidy` in `~/.claude/CLAUDE.md`) (the `tidy` skill's catch-all list).
   - Return a short list of anything unsure or stale. Relay it.
2. **Check** the data before building: drop asks the user already answered in this session, and links that are not `https://`.
3. **Build**: `python3 ~/.claude/skills/project-status/build.py ~/.claude/project-status/projects.json <scratchpad>/project-status.html --config ~/.claude/project-status/config.json --home ~/.claude/project-status`. Relay any `warning: unlinked mention` lines it prints and fix them (see "Links").
4. **Publish** in a one-shot sonnet agent (general-purpose): it builds (step 3), publishes the file with the Artifact tool to `artifact_url` from config (it reads the artifact first when its session needs that), and returns only the link and the version. The main session never reads the artifact, the built HTML or `projects.json`. Without an `artifact_url`, the agent publishes new and saves the link to config. The page is private to the user.
5. Tell the user the link, what changed since the last build, and the unsure list. Percentages are estimates; say so once.

## Small updates (keep it in sync)

The page should never lag the work. When one fact changes (a PR merged, a run finished, the user decided something, a reply arrived, a wait cleared), do not gather again:

1. Hand the change, in one line (what changed, which project or one-off), to a one-shot sonnet publisher agent. It edits `~/.claude/project-status/projects.json` in place by the rules below (the item's `state`, the project's `needs_me`, the matching `waiting_on` row, one new `recent_progress` line, `progress_pct` when a milestone or ticket closed (keep `progress_basis` true), `as_of` set to now UTC), builds and publishes as in Refresh step 4, and returns the link and one line on what changed.
2. The main session never opens the data file.
3. Say what changed in one line. Do not ask first.

Do this without being asked, every time such a fact lands in the session. The `board` skill does it on every sync and every landed event, and writes the page link as the first line of each daily row's `## Your TODOs`.

## Inbox

The inbox is worked out at build time from these sources. Feed items clear themselves; nobody ticks them.

| Source | Writer | Items |
|---|---|---|
| `projects[].needs_me[]` | gather agent, session | ask |
| `one_offs[]` with `needs_me` and not done | `add_oneoff.py` | one-off |
| `waiting_on[]` whose `nudge_due` is today or past | gather agent, session | nudge |
| `feeds/github.json` | `status-feeds` | review requests aimed at the user; for the user's own PRs one of fix conflict, fix CI, reply to review, merge |
| `feeds/slack.json` | `status-feeds` (from the Slack poll's triage log) | Slack asks held as not-now |
| `inbox.json` | the session, through `inbox.py` | approve an agent, send a draft, confirm a delivery, a TODO, an ask |

The session writes `inbox.json` only through `inbox.py` (`python3 ~/.claude/skills/project-status/inbox.py --help`):

- `add --kind K --title T [--link URL] [--id ID] ...`: an agent is held on an approval, a draft is waiting to be sent, a delivery passes its confirm-by date, or the user asks for a TODO.
- `done <id or title text>`: when the fact lands, the same moment as "Small updates".
- `snooze <id> --until YYYY-MM-DD`: the user says "later" with a date. Only `inbox.json` items can be snoozed.
- `meeting --title T --at ISO`: at rollover, only when the session knows the next meeting.
- `sync --origin board --file F`: the `board` skill's mirror on every sync.

Items with the same link merge into one (the session's words, the feed's live state). Ticket keys are never used to merge.

## Long jobs

A job that runs for days (a backfill, a big export) shows as a bar with a finish date on its project page, on the project row and on the timeline. The page works out the percent, the finish date (from `per_day`, counted from the last report, so a job that stops reporting goes late) and whether it is stale.

- After each progress report: `python3 ~/.claude/skills/project-status/job.py ~/.claude/project-status/projects.json set <project_id> "<label>" --done N --total N [--unit files] [--per-day N] [--eta YYYY-MM-DD]`. Only the fields given change.
- When it finishes: `... job.py ~/.claude/project-status/projects.json done <project_id> "<label>"`. The job goes and a "Finished <label>" line lands in recent progress.
- Then hand the publish to the one-shot publisher (Refresh step 4).

## Links

Every ticket key, PR, Notion page, Slack thread, run or doc the page names is drawn as a link. The rule lives in `derive.py` (`link_mentions`), with the link bases from local config only:

- Ticket keys (`ENG-142`): `tracker_url` plus the key.
- `repo #123`: a PR in `github_org`.
- Slack triage keys (`C0123ABC:1768000000.123456`): `inbox.slack_url`.
- Anything else named by a key: `links.patterns`, a list of `{"match": "<regex with one group>", "url": "<base>{1}"}`.
- Notion pages, docs and threads have no key, so they link only through the item's own `link`, `ref` or `links[]` field.

The build prints `warning: unlinked mention <text> at <where> (<why>)` for a key with no base configured, or a row that names a thread, page or doc but has no link, and the page footer lists them. Fix the data (add the link) or the config (add the base); the build never fails on them.

## One-offs

When the user says "add a one-off", "put X on the status page" or "X is done":

- Add: `python3 ~/.claude/skills/project-status/add_oneoff.py ~/.claude/project-status/projects.json "Title" [--needs-me] [--due YYYY-MM-DD] [--note "..."] [--ref TICKET-1] [--state "in progress"] [--pct 40]`. Only the title is required.
- Finish: `... add_oneoff.py ~/.claude/project-status/projects.json --done "part of the title"`
- Then hand the publish to the one-shot publisher (Refresh step 4). No gathering needed.

A one-off that grows (several steps, other people, a deadline) becomes a project: add a `projects` entry with just `id`, `name` and `progress_pct`, and fill in more later. Every other field is optional.

## Changing the page

- Edit `page.css` and `page.js` for layout, `derive.py` for every number, date and rule the page shows, `build.py` for the data contract. `page.js` only lays out what `derive.py` worked out. Keep all of them generic: no names, links or brand colors.
- The design brief, from the user: visual first (shapes before text), clean and minimal, home is glance-only and reads as a dashboard, navigation in the rail. Coral only for something late. New classes get a prefix (`.tl-`, `.pl-`, `.kp-`, `.th-`, `.ag-`, `.jb-`, `.sp-`, `.rl-`) so they never clash.
- After a change, run `node --check skills/project-status/page.js` and the tests, then build with `sample-data.json` and `sample-home/` before publishing.

## Common mistakes

| Mistake | Fix |
|---|---|
| Putting company colors, names or links in `page.css`, `page.js` or `template.html` | They go in `~/.claude/project-status/config.json` |
| Publishing a new Artifact on every refresh | Pass `artifact_url` as `url` so the link stays the same |
| Details creeping onto home | Home is numbers, the top inbox rows and cards only. Detail goes on the inbox and project pages |
| Hand-editing `inbox.json` | Use `inbox.py`, the file's only writer |
| Adding a GitHub review or PR state by hand | The `status-feeds` GitHub feed does it |
| Building without `--home` | The page then shows no inbox.json, GitHub or Slack items |
| Coral for counts or needs-you badges | Coral only for something late; counts stay neutral |
| Listing things the user is waiting on under `needs_me` | Those are `waiting_on` rows |
| Overwriting `one_offs` during a gather | The gather agent keeps them as they are |
| Gathering, editing the data file or publishing in the main session | Agents do all three; the main session passes one line and relays the link |
| Running Artifact quickstart for the status page | It exists. Publish to `artifact_url` |
| Hand-editing `jobs` in `projects.json` | Use `job.py`, so `updated` and the finish date stay right |
| Brand colors in `page.css` | They go in the local `theme.light` and `theme.dark` |
| Per-person stats or names in `stats.json` | Stats are aggregates for me and my team only |
| A ticket key or thread named with no link | Add the link to the item, or the link base to config |
