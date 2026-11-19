---
name: project-status
description: Use when the user asks for a visual status of their projects, a project dashboard or status page, to refresh or republish it, or to add, change or finish a one-off item on it.
---

# Project status

A visual status page, published as a private Artifact. It is built for looking, not reading: a progress ring per project, a status bar split by state, a count badge when something needs the user, and due-date chips. Detail lives on each project's own page.

Pages, all behind the menu button:

- **Overview**: quick glance only. A few numbers and one card per project.
- **One page per project**: what is needed from the user first, then where it stands, then the full breakdown in collapsible groups, people it waits on, recent decisions and progress, links.
- **People you are waiting on**: everything owed by someone else, grouped by person.
- **One-offs**: small standalone items that belong to no project.

Nothing in this skill names a company, person or project. Those come from the data and config files.

## Files

| File | What it is |
|---|---|
| `template.html` | The page. Neutral colors, no names or links baked in |
| `build.py` | Turns a data file (and an optional config) into the page. The data format is in its docstring |
| `add_oneoff.py` | Adds or finishes a one-off in the data file |
| `config.example.json` | Starter config: title, tracker and GitHub link bases, footer note, color overrides |
| `sample-data.json` | Made-up data to try the page with |

Per-machine files live outside the repo, in `~/.claude/project-status/`:

- `config.json`: copied from `config.example.json` and filled in. Also holds `artifact_url` once the page is published.
- `projects.json`: the current data.

## Setup (once per machine)

1. `mkdir -p ~/.claude/project-status`
2. `cp ~/.claude/skills/project-status/config.example.json ~/.claude/project-status/config.json` and fill in `title`, `tracker_url` (the prefix a ticket key is added to), `github_org` and `source_note`. Delete a line you do not need.
3. Colors: the `theme.light` block overrides the page's color tokens (the full list is the `:root` block at the top of `template.html`). The usual change is `--canvas` (page background), `--accent` and `--accent-soft` (progress), `--strong` (headings) and `--font`. Keep it calm: one background color, white cards, one accent. If the user has a design system, take the values from it and keep them in this local config, never in the repo.
4. Try it with the sample: `python3 ~/.claude/skills/project-status/build.py ~/.claude/skills/project-status/sample-data.json /tmp/project-status.html --config ~/.claude/project-status/config.json`, then publish that file with the Artifact tool to see the look.
5. First real build: follow "Refresh" below. After the first publish, save the Artifact link as `artifact_url` in `config.json` so later sessions update the same page.

If `~/.claude/project-status/config.json` is missing, do steps 1 and 2 with the user before anything else.

## Refresh

1. **Gather** the data into `~/.claude/project-status/projects.json`, in the format from `build.py`'s docstring. Dispatch one read-only agent for this (pass `model`); it writes only that file. Sources, in order: the user's project notes (for the `board` skill, the `Projects data source` line of `### Work board` in `~/.claude/CLAUDE.md`, plus today's board row), then the tracker and GitHub only for gaps. Rules for the agent:
   - `needs_me` holds only what the user must do or decide by hand. What waits on someone else goes in `waiting_on`. What an agent can do alone goes in neither.
   - `progress_pct` comes from real milestones or tickets, and `progress_basis` says how in one sentence. Never invent precision.
   - Keep `one_offs` already in the file. They are the user's own list.
   - Plain English, short sentences. Leave out finished projects.
   - Skip the Projects row named by the `Loose ends` line of `### Tidy` in `~/.claude/CLAUDE.md` (the `tidy` skill's catch-all list).
   - Return a short list of anything unsure or stale. Relay it.
2. **Check** the data before building: drop asks the user already answered in this session, and links that are not `https://`.
3. **Build**: `python3 ~/.claude/skills/project-status/build.py ~/.claude/project-status/projects.json <scratchpad>/project-status.html --config ~/.claude/project-status/config.json`
4. **Publish** the built file with the Artifact tool. With an `artifact_url` in config, pass it as `url` (read the artifact first if this session has not published it). Without one, publish new and save the link to config. The page is private to the user.
5. Tell the user the link, what changed since the last build, and the unsure list. Percentages are estimates; say so once.

## Small updates (keep it in sync)

The page should never lag the work. When one fact changes (a PR merged, a run finished, the user decided something, a reply arrived, a wait cleared), do not gather again:

1. Edit `~/.claude/project-status/projects.json` in place: the item's `state`, the project's `needs_me`, the matching `waiting_on` row, one new `recent_progress` line, and `progress_pct` when a milestone or ticket closed (keep `progress_basis` true). Set `as_of` to now (UTC).
2. Build and publish to the same link (steps 3 and 4 of Refresh).
3. Say what changed in one line. Do not ask first.

Do this without being asked, every time such a fact lands in the session. The `board` skill does it on every sync and every landed event, and writes the page link as the first line of each daily row's `## Your TODOs`.

## One-offs

When the user says "add a one-off", "put X on the status page" or "X is done":

- Add: `python3 ~/.claude/skills/project-status/add_oneoff.py ~/.claude/project-status/projects.json "Title" [--needs-me] [--due YYYY-MM-DD] [--note "..."] [--ref TICKET-1] [--state "in progress"] [--pct 40]`. Only the title is required.
- Finish: `... add_oneoff.py ~/.claude/project-status/projects.json --done "part of the title"`
- Then build and publish (steps 3 and 4 above). No gathering needed.

A one-off that grows (several steps, other people, a deadline) becomes a project: add a `projects` entry with just `id`, `name` and `progress_pct`, and fill in more later. Every other field is optional.

## Changing the page

- Edit `template.html` for layout, `build.py` for the data contract. Keep both generic: no names, links or brand colors.
- The design brief, from the user: visual first (shapes before text), clean and minimal, overview is glance-only, navigation in a menu.
- After a template change, build with `sample-data.json` and check the page script still parses before publishing (`node --check` on the inline script is enough).

## Common mistakes

| Mistake | Fix |
|---|---|
| Putting company colors, names or links in `template.html` | They go in `~/.claude/project-status/config.json` |
| Publishing a new Artifact on every refresh | Pass `artifact_url` as `url` so the link stays the same |
| Details creeping onto the overview | Overview is numbers and cards only. Detail goes on the project page |
| Listing things the user is waiting on under `needs_me` | Those are `waiting_on` rows |
| Overwriting `one_offs` during a gather | The gather agent keeps them as they are |
| Gathering data in the main session | One read-only agent writes the data file; the main session builds and publishes |
