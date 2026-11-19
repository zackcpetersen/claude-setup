# Setup on a New Machine

Everything in this repo is generic - nothing references a specific company, repo, or tracker. Commands are fully generic and read machine-specific values from `~/.claude/CLAUDE.md` and `~/.claude/config/`. `FILL IN` markers remain only in `claude-md/` and `bin/worktree`. This file walks through all of them.

## What's in here

| Path | What it is | Installed to |
|---|---|---|
| `commands/pr.md` | `/pr` - commit, create PR, self code review + babysit CI until green | `~/.claude/commands/` (symlink) |
| `commands/babysit-pr.md` | `/babysit-pr` - unblock all open PRs (CI, comments, conflicts) | `~/.claude/commands/` (symlink) |
| `commands/self-review.md` | `/self-review` - subagent review of a plan or implementation | `~/.claude/commands/` (symlink) |
| `commands/start-ticket.md` | `/start-ticket` - fetch ticket, produce implementation plan | `~/.claude/commands/` (symlink) |
| `skills/write-as-zack/` | `write-as-zack` skill - writing-voice rules, with an optional live voice page | `~/.claude/skills/` (symlink) |
| `skills/board/` | `board` skill - daily Notion work board plus sub-agent ticket orchestration | `~/.claude/skills/` (symlink) |
| `skills/reviewing-prs/` | `reviewing-prs` skill - the review rules both `review-pr` and `pr` read first | `~/.claude/skills/` (symlink) |
| `skills/review-pr/` | `review-pr` skill - review a teammate's PR, approve or comment with per-comment approval | `~/.claude/skills/` (symlink) |
| `skills/daily-auth/` | `daily-auth` skill - check and fix every login the day needs, from `~/.claude/auth-checks.json` | `~/.claude/skills/` (symlink) |
| `skills/sync-repos/` | `sync-repos` skill - fast-forward every repo in `~/.claude/sync-repos.json` to `origin/main` | `~/.claude/skills/` (symlink) |
| `skills/project-status/` | `project-status` skill - a visual project status page (progress rings, status bars, needs-you badges) built from a data file and published as a private Artifact | `~/.claude/skills/` (symlink) |
| `skills/watch/` | `watch` skill - background waits on PRs, deploys and Dagster runs that wake the session once, plus a cheap 5-minute Slack poll that wakes the session only when you are messaged | `~/.claude/skills/` (symlink) |
| `output-styles/direct.md` | "Direct" output style - answer first, plain english, no hedging | `~/.claude/output-styles/` (symlink) |
| `output-styles/momentum.md` | "Momentum" output style - Direct plus progress tracking and one next action | `~/.claude/output-styles/` (symlink) |
| `output-styles/tldr.md` | "TLDR" output style - 1-3 sentences, expands only on request | `~/.claude/output-styles/` (symlink) |
| `bin/query_db` | Read-only Postgres query helper | `~/bin/` (symlink) |
| `bin/worktree` | Multi-repo git worktree manager | `~/bin/` (symlink) |
| `bin/wait-for` | Background wait the `watch` skill starts: PR, deploy, Dagster run or Slack poll, one event line then exit (Python 3 standard library; tests in `bin/tests/`) | `~/bin/` (symlink) |
| `bin/pr-precheck` | Lints changed files with autocorrect and runs only their tests, once before the first push; also a read-only `report` and a pre-push `hook` mode (Python 3 standard library; tests in `bin/tests/`) | `~/bin/` (symlink) |
| `bin/worktree-config.example.json` | Starter config for `worktree` | copy + edit, see below |
| `config/*.example.*` | Per-skill config examples (board, watch, tidy, writing voice, optional self-review and pr-precheck) | the four `.md` files are copied to `~/.claude/config/` when absent, see below |
| `plugins/model-discipline/` | `model-discipline` plugin - the agent-model-guard hook, a SessionStart rules block, and the `playbook` skill | `/plugin install`, see section 4 |
| `plugins/plan-gate/` | `plan-gate` plugin - blocks `ExitPlanMode` until `/self-review` records a pass | `/plugin install`, see section 4 |
| `plugins/new-day/` | `new-day` plugin - nudges every prompt until `daily-auth` has run today | `/plugin install`, see section 4 |
| `claude-md/CLAUDE.md.template` | Generic user-level Claude Code preferences | copied to `~/.claude/CLAUDE.md` if absent |
| `claude-md/MANIFESTO.md` | "The Ten Laws" design-philosophy template to drop into any repo | copy into a repo by hand, fill in the examples |
| `install.sh` | Does the linking/copying above | - |
| `update.sh` | Pulls, re-runs `install.sh`, and prints what needs per-machine action since your last sync | run after the nudge, see "Updating an existing machine" |

Symlinks mean edits made on any machine land in this repo's working tree - commit and push to back them up.

## 1. Prerequisites

- Claude Code installed and logged in
- `gh` CLI installed and authenticated (`gh auth login`) - needed by `/pr` and `/babysit-pr`
- The built-in `/code-review` skill (ships with Claude Code) - needed by `/pr`'s self review step
- `jq` - needed by `worktree`
- `psql` - needed by `query_db`
- Make sure `~/bin` is on your `PATH`

## 2. Install

```bash
git clone git@github.com:zackcpetersen/claude-setup.git
cd claude-setup
./install.sh
```

On a fresh install (no `~/.claude/CLAUDE.md` yet), `install.sh` also copies `config/board.example.md`, `watch.example.md`, `tidy.example.md` and `writing-voice.example.md` to `~/.claude/config/<name>.md`. On an existing install it never copies them: it only says which ones are missing, because a missing section can mean you turned that skill off. Copy the ones you want by hand. Skills and scripts read both places; a filled-in value in `~/.claude/config/` wins.

## Updating an existing machine

```bash
~/Projects/claude-setup/update.sh
```

That pulls `origin/main`, re-runs `install.sh`, and prints only what changed since the last time it ran: the commits, the changelog entries below that need a manual step, any template sections added since then that your `~/.claude/CLAUDE.md` lacks, leftover `.bak` files, and whether the installed plugin cache has drifted from the repo. It records the synced commit in `~/.claude/.claude-setup-synced`. The SessionStart nudge hook in section 4 tells you when the clone is behind, so you never have to remember to check.

The manual equivalent, and what `update.sh` does under the hood:

1. Relink. Pick one:
   - `./install.sh` relinks everything: commands, skills, output styles, and
     the `~/bin` scripts. Existing regular files are moved to `<name>.bak`.
     If your `~/bin/query_db` or `~/bin/worktree` are older customized copies,
     this replaces them with the generic versions, so check first.
   - Or link only the commands (mirror the loop for `skills/*/` and
     `output-styles/*.md` if those changed too):

   ```bash
   for f in "$PWD"/commands/*.md; do
     dest="$HOME/.claude/commands/$(basename "$f")"
     if [ -e "$dest" ] && [ ! -L "$dest" ]; then mv "$dest" "$dest.bak"; fi
     ln -sfn "$f" "$dest"
   done
   ```

   Commands that exist only on this machine are not touched either way.
2. Diff `~/.claude/CLAUDE.md` against `claude-md/CLAUDE.md.template`. Copy over every
   section the repo has that yours lacks, and fill in each FILL IN with this
   machine's values. Work through the changelog below for the ones that need
   action.
3. Open section 4 below and compare each remaining snippet (the update
   nudge) against the `hooks` block of `~/.claude/settings.json`. Paste in
   any that are missing or differ. Install any plugins from section 4 that
   `/plugin list` does not show.
4. Confirm: `ls -la ~/.claude/commands/` shows symlinks into the repo, and
   `/pr`, `/babysit-pr`, `/self-review`, `/start-ticket` appear exactly once
   in the slash command list.
5. For each `.bak`: `diff <name>.bak <name>`. If the `.bak` has anything the
   repo file lacks, port it into the repo file and commit. Only then delete
   the `.bak`. A `.bak` is only ever written when a regular file is replaced,
   so once the link exists no later run will recreate it. Diff before deleting.

### Changelog: changes that need per-machine action

Newest first. Only entries that need a manual step; delete entries older
than 6 months.

- 2026-11-<merge day>: Workflow and self-review changes. Per machine: run
  ./update.sh; reinstall model-discipline (version 1.2.0, the update.sh
  output has the command) and restart; optionally move the ### Work
  board, ### Watches, ### Tidy and ### Writing voice sections from
  ~/.claude/CLAUDE.md into ~/.claude/config/<board|watch|tidy|writing-voice>.md
  (scripts and skills read both places); copy the new template lines
  (Standing default, CI/CD exception, Handoffs size, Issue Tracker,
  External Communications, Review comments, No-ticket repos) into
  ~/.claude/CLAUDE.md; add `Slack poll quiet: none` to keep every Slack
  message waking the session (the new default filters acks, bot posts
  and FYIs).
- 2026-11-19: New `tidy` skill and `~/bin/tidy` (scheduled cleanup at
  board wrap, rollover and a weekly deep clean). Per machine: re-run
  `./install.sh`, add the `### Tidy` block from the template to
  `~/.claude/CLAUDE.md`, then run `/tidy weekly --dry-run` once and read
  the report before any real run.
- 2026-11-17: New `project-status` skill (a visual project status
  page). Per machine: re-run `./install.sh` to link it, then follow
  "`skills/project-status/SKILL.md`" in the fill-in checklist
  (`~/.claude/project-status/config.json`).
- 2026-11-17: The hourly Slack sweep is retired. `~/bin/wait-for slack`
  polls Slack every 5 minutes on the cheapest model (about half a cent
  a poll, around 9 seconds) and wakes the session only when someone
  messaged you. Board sync took over the sweep's other jobs (NUDGE? and
  PROPOSE). Per machine: re-run `./install.sh`; add the new
  `Slack poll` lines from the `### Watches` block of the template to
  `~/.claude/CLAUDE.md` (set `Slack poll: on`, list your user groups);
  delete any hourly sweep cron (`CronList`, `CronDelete`); check it
  with `~/bin/wait-for slack --once` (prints `SLACK ...` or `NOTHING`;
  add `--since 2h` to look further back). Needs the `claude` command on
  the PATH and the Slack MCP plugin signed in.
- 2026-10-31: The `watch` skill dropped its registry. `bin/watch` is
  gone; waits are background `~/bin/wait-for` commands and Slack is
  swept hourly. Per machine: re-run `./install.sh`; `rm ~/bin/watch`;
  archive or delete `~/.claude/watches.json`; trim the `### Watches`
  block to the template (drop Registry, Tick interval, Quiet hours,
  Requests channel and the email connector); repoint the Work board
  `Watch-slack state file` line to `~/.claude/watch-sweep.json`; delete
  any `/watch tick` cron job; in `~/.claude/settings.json` replace
  `Bash(~/bin/watch *)` with `Bash(~/bin/wait-for *)`, keep the Slack
  read tools and `slack_send_message_draft`, and drop the watch-only
  lines `mcp__claude_ai_Gmail__{get_thread,get_message,search_threads,
  create_draft,update_draft}`, `<notion prefix>notion-fetch` and
  `<notion prefix>notion-update-page` unless other skills still use them.
- 2026-10-28: New `watch` skill and `bin/watch` script. Re-run
  `./install.sh` to link `~/bin/watch`; add the `### Watches` block from
  the template; add the allow rules listed in `skills/watch/SKILL.md`;
  reword your watch-slack posting carve-out to name the `watch` skill;
  then retire `~/.claude/commands/watch-slack.md`.
- 2026-10-22: Several changes, each needs a step:
  - Re-run `./install.sh` so the new `daily-auth` and `sync-repos` skills
    get linked into `~/.claude/skills/`.
  - The template gained a `## Handoffs` section (set `Handoff folder:`,
    e.g. `~/handoffs/`, and create the folder) and new rules under
    `## General Preferences`, `## Communication Style` and
    `## Git and Version Control`. Copy them into your CLAUDE.md.
  - The `Access checks` bullets under `### Work board` moved to
    `~/.claude/auth-checks.json`, run by the new `daily-auth` skill. Convert
    your bullets using `skills/daily-auth/auth-checks.example.json`, then
    replace the bullet list with the template's one-line pointer.
  - New `sync-repos` skill: create `~/.claude/sync-repos.json` from
    `skills/sync-repos/sync-repos.example.json`.
  - Run `/plugin marketplace update claude-setup` first, so the
    marketplace knows about the plugin changes below.
  - New `new-day` plugin: `/plugin install new-day@claude-setup`.
  - model-discipline is now 1.1.0 (adds the sub-agent rules appender).
    Run `/plugin uninstall model-discipline@claude-setup` and
    `/plugin install model-discipline@claude-setup`.
  - Restart Claude Code afterwards, since hooks load at session start.
- 2026-10-13: The plan gate is now the `plan-gate` plugin. Remove the
  inline `ExitPlanMode` hook from `~/.claude/settings.json` BEFORE
  installing plan-gate (`/plugin install plan-gate@claude-setup`). Running
  both locks plan mode.
- 2026-09-23: The commit message format left `/pr`. CLAUDE.md's
  `## Git and Version Control` section now has a `Commit message format:`
  line (default `type: description`). Set yours, e.g.
  `[TICKET] type: description`, or `/pr` falls back to the default.
- 2026-09-23: The "do NOT run tests or linters locally" rule left the CLAUDE.md
  template; it is a per-machine time saver for CI setups that re-run
  everything. The `## CI/CD Policy` section is now a FILL IN. Keep the rule
  in your own CLAUDE.md or drop it; nothing else changes.
- 2026-09-22: CLAUDE.md gained `### Issue Tracker` (tracker, MCP plugin,
  ticket URL format, write-confirmation rule). `/pr` and `/start-ticket`
  read it instead of hardcoding values. Add it to your CLAUDE.md.
- 2026-09-22: CLAUDE.md gained `### Writing voice` (optional voice page URL).
  The `write-as-zack` skill reads it instead of holding the URL itself, so the
  skill directory can be symlinked. Add the section if you use a voice page.
- 2026-09-22: `/pr` runs a background self code review (`--review-effort`,
  default medium, opus). Copy the updated `### Finalize PR (/pr)` paragraph
  from `claude-md/CLAUDE.md.template` into yours. Needs the built-in `/code-review`
  skill (ships with Claude Code). No other setup.

## 3. Fill-in checklist

Work through these once per machine:

### `~/.claude/CLAUDE.md`
`install.sh` copies the starter file only if you don't already have one. Open it and fill in every `FILL IN` comment:
- Per-repo notes for the query_db section (which `.env.db.*` files exist, which envs are production)
- The Issue Tracker section (tracker, MCP plugin, ticket URL format)
- Any other machine-specific tools (log search, tracker MCP, etc.)
- The Repo Conventions table (one row per repo: default branch, test command, lint command)
- The `## Handoffs` folder line (e.g. `~/handoffs/`); create the folder with `mkdir -p`

### `skills/daily-auth/SKILL.md`
- No file edits. Copy `skills/daily-auth/auth-checks.example.json` to `~/.claude/auth-checks.json` and list every login and credential this machine needs (cloud SSO, `gh`, SSH keys, VPN, database env files, MCP servers, browser consoles). The skill writes `~/.claude/daily-auth-last-run.json` each day; the `new-day` plugin reads it.

### `skills/sync-repos/SKILL.md`
- No file edits. Copy `skills/sync-repos/sync-repos.example.json` to `~/.claude/sync-repos.json` and list the repo paths to keep current.

### `commands/start-ticket.md`
- Needs your issue tracker's MCP tools available (e.g. install the Atlassian plugin for Jira, or your tracker's equivalent). No file edits required.

### `skills/write-as-zack/SKILL.md`
- No file edits. Copy `config/writing-voice.example.md` to `~/.claude/config/writing-voice.md` (install.sh does this only on a fresh install) and fill it in. The optional voice page URL lives there; delete that bullet to run on the rules written into the skill, which are complete on their own. The rules are Zack's; edit them to describe your own voice.

### `skills/board/SKILL.md`
- No file edits. Copy `config/board.example.md` to `~/.claude/config/board.md` (install.sh does this only on a fresh install) and fill it in. The skill stops with a clear message if it is missing.
- Create one empty Notion page with an inline database (any name, only the default title property) and put its URL on the `Board page` line. The skill adds the columns it needs on first run.
- Optional: add the `Projects data source` line. On the first run the skill creates a "Projects" database under the board page with the schema in `page-template.md` and gives you the `collection://` id to paste back; after that it keeps one page per workstream current.
- Needs the Notion MCP plugin, the Slack MCP plugin, your tracker's MCP plugin, `gh`, and `~/bin/worktree` with its config. The ticket flow also needs `/start-ticket`, `/self-review`, `/pr` and the built-in `/code-review` skill.
- The watch-slack state file path (`~/.claude/watch-sweep.json`); it holds the declined list for the sync's NUDGE? and PROPOSE questions.

### `skills/watch/SKILL.md`
- No file edits. Copy `config/watch.example.md` to `~/.claude/config/watch.md` (install.sh does this only on a fresh install) and fill it in; the skill stops with a clear message if it is missing.
- Slack poll lines: `Slack poll` (on or off), `Slack poll every`, `Slack poll model`, `Slack poll triggers`, `Slack poll user groups` (the Slack tools cannot list your groups, so type them), `Slack poll keywords`, `Slack poll ignore`, `Slack poll quiet` (hints that never wake the session, default `ack, bot, fyi`, `none` turns it off), `Slack poll state file`, and the optional group DM lines `Slack poll group-dms` (aimed-only or all, default aimed-only), `Slack poll group-dms lookback` (default 60m) and `Slack poll user name`. Check with `~/bin/wait-for slack --once`.
- Add the allow rules listed in the skill's Install section to `~/.claude/settings.json` by hand: `Bash(~/bin/wait-for *)` plus the Slack read tools and `slack_send_message_draft`, so triage and drafts never stop on a permission prompt.
- Needs `gh`, Python 3, and `~/bin/wait-for` (linked by `install.sh`). The Slack poll needs the `claude` command and the Slack MCP plugin; Dagster waits need the `Dagster` config line.

### `skills/project-status/SKILL.md`
- No file edits. Per-machine files live in `~/.claude/project-status/`: `mkdir -p ~/.claude/project-status`, copy `skills/project-status/config.example.json` there as `config.json` and fill in the title, the tracker link prefix, the GitHub org and (optional) your colors under `theme.light`. Brand colors stay in that local file, never in the repo.
- Try it: `python3 ~/.claude/skills/project-status/build.py ~/.claude/skills/project-status/sample-data.json /tmp/project-status.html --config ~/.claude/project-status/config.json`, then ask Claude to publish that file as an Artifact.
- Then ask Claude for "my project status page". It gathers your projects into `~/.claude/project-status/projects.json`, builds, publishes, and saves the Artifact link in `config.json` so every refresh updates the same page. "Add a one-off: ..." adds a standalone item.
- Needs Python 3 and the Artifact tool. Reads the board's `Projects data source` when you use the `board` skill; without it, tell Claude where your project notes live.

### `skills/tidy/SKILL.md`
- No file edits. Copy `config/tidy.example.md` to `~/.claude/config/tidy.md` (install.sh does this only on a fresh install) and fill it in: the weekly day, any extra repos and report folders, the ages, the Loose ends name, and any `Never touch` paths. Without the section tidy only lists leftovers and changes nothing.
- With a `Projects data source`, create one Projects row with the Loose ends name and Status Parked.
- Check with `~/bin/tidy scan --mode weekly --no-fetch` (read-only; exit 2 means a config problem it names), then `/tidy weekly --dry-run`.
- Needs `git`, `gh`, Python 3 and `~/bin/tidy` (linked by `install.sh`).

### `skills/review-pr/SKILL.md`
- No file edits. Needs `gh` and the built-in `/code-review` skill. Uses the writing-voice skill named in `~/.claude/config/writing-voice.md` (copy `config/writing-voice.example.md`) when present, otherwise only the `reviewing-prs` comment rules it pastes into `dispatch-prompt.md`.

### `bin/pr-precheck`
- No script edits. `~/bin/pr-precheck fix` lints changed files with autocorrect and runs only the tests tied to them, once before the first push; `report` prints size, stale generated files and calls inside a lock for the reviewer; `hook` is a check-only pre-push hook (section 4).
- Optional: copy `config/pr-precheck.example.json` to `~/.claude/config/pr-precheck.json` for per-repo overrides (a changed-test command, `"tests": "none"`, skipped languages, generated files).
- Check with `~/bin/pr-precheck report` inside any repo.

### `~/.claude/config/self-review.md`
- Optional. Copy `config/self-review.example.md` and add one `## <repo folder name>` heading per repo with checks `/self-review` applies on top of its generic ones.

### `bin/query_db`
- No script edits needed - it's fully generic: `query_db <env-file> "<sql>"`.
- In each repo you want to query, create gitignored `.env.db.<env>` files at the repo root (e.g. `.env.db.local`, `.env.db.cloud`) with `DATABASE_HOST`, `DATABASE_PORT` (optional, default 5432), `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`.
- **Verify the repo's `.gitignore` covers them** (`git check-ignore .env.db.local`) before creating them - they are credentials. Never commit them.
- All queries run with `default_transaction_read_only=on`, so writes fail.
- To let Claude Code run it without prompting, add `"Bash(query_db:*)"` (plus the `~/bin/query_db` and absolute-path variants) to the `permissions.allow` list in `~/.claude/settings.json`.

### `bin/worktree`
- Copy `bin/worktree-config.example.json` to `~/bin/.worktree-config.json` (the script looks for its config next to wherever it's invoked from, which is `~/bin` with the symlink layout). Edit it: one entry per repo with `repo_path`, `worktree_base`, `default_branch`, and which untracked files/dirs to copy into each new worktree (`copy_files` / `copy_directories`), plus an optional `dependencies.command` to run after checkout. The config stays in `~/bin`, outside this repo, since it's machine-specific.
- Optional: to use `worktree cleanup`, create a `ticket-status` helper next to the script. The full contract and a copy-paste Jira example live in the `TICKETING INTEGRATION` comment inside `bin/worktree`.

## 4. Claude Code settings to recreate (not stored here)

`~/.claude/settings.json` is deliberately NOT in this repo - it can contain secrets (tokens in its `env` block). Recreate the useful bits by hand:

```json
{
  "permissions": { "defaultMode": "auto" }
}
```

### model-discipline plugin (the agent-model-guard hook)

The guard is a PreToolUse hook on the `Agent` tool. On a session running an expensive model, it denies subagent dispatches that omit `model` when the agent definition has no `model:` pin - an unpinned dispatch silently inherits the expensive session model. It ships as a plugin, so there is no hook JSON to paste. Full description: [plugins/model-discipline/README.md](plugins/model-discipline/README.md).

Install it from GitHub:

```
/plugin marketplace add zackcpetersen/claude-setup
/plugin install model-discipline@claude-setup
```

Or from your local clone, if you are testing your own edits:

```
/plugin marketplace add ~/Projects/claude-setup
/plugin install model-discipline@claude-setup
```

Restart Claude Code afterwards - hooks load at session start.
The same two steps from a plain shell, for scripts or an agent doing the setup for you:

```bash
claude plugin marketplace add zackcpetersen/claude-setup
claude plugin install model-discipline@claude-setup
```


Notes:

- **Remove any hand-pasted `Agent|Task` entry from `hooks.PreToolUse` in `~/.claude/settings.json`.** Earlier versions of this file told you to wire the guard in by hand. A plugin hook and an identical settings.json hook both fire, so leaving the old entry runs the guard twice.
- `CLAUDE_EXPENSIVE_MODEL_PREFIX` sets which session model the guard polices. Default `claude-fable`; set it to `claude-opus` if opus is your top tier.
- **The session model is a user-settings value; no plugin can set it.** If you want the top model by default, put `"model": "claude-fable-5-1[1m]"` in `~/.claude/settings.json` yourself.
- Both the local-path and GitHub registrations use the marketplace name `claude-setup`, so run `/plugin marketplace remove claude-setup` before switching between them.
- Installed plugins are cached copies under `~/.claude/plugins/cache/`, not live links. After editing the guard, run `/plugin marketplace update claude-setup`, then uninstall and reinstall (`/plugin uninstall model-discipline@claude-setup`, `/plugin install model-discipline@claude-setup`) - `plugin update` and a bare `install` are no-ops while the version in `plugin.json` is unchanged. Or run `claude --plugin-dir ~/Projects/claude-setup/plugins/model-discipline` while you iterate. `update.sh` reports when the cache has drifted.

The plugin also ships two newer hooks: `context-warn` (PostToolUse) tells the main session once when its context passes `CLAUDE_CONTEXT_WARN_AT` tokens (default 150000; `0` or `off` turns it off), and `review-target-guard` denies `/code-review` with a bare PR number.

### Pre-push lint hook (optional)

Add a PreToolUse Bash entry to `~/.claude/settings.json` so every `git push` from Claude is lint-checked (Ruby only by default; `hook_langs` in `~/.claude/config/pr-precheck.json` opts other languages in). It fails open on any error. If you used a hand-made pre-push hook, replace it with this one.

```json
{"matcher":"Bash","hooks":[{"type":"command","command":"~/bin/pr-precheck hook","timeout":120}]}
```

### Update nudge hook (tells you when this repo is behind)

Once a day, on session start, this fetches `origin/main` for the clone at `~/Projects/claude-setup` and prints a one-line nudge into the session context if the clone is behind. It prints nothing when current and fails silently offline. Add it to `hooks.SessionStart` in `~/.claude/settings.json` (adjust the path if you cloned elsewhere):

```json
{
  "matcher": "startup",
  "hooks": [
    {
      "type": "command",
      "command": "d=\"$HOME/Projects/claude-setup\"; [ -d \"$d/.git\" ] || exit 0; f=\"$d/.git/FETCH_HEAD\"; if [ ! -f \"$f\" ] || [ -n \"$(find \"$f\" -mmin +1440 2>/dev/null)\" ]; then git -C \"$d\" fetch -q origin main >/dev/null 2>&1 || exit 0; fi; n=$(git -C \"$d\" rev-list --count HEAD..origin/main 2>/dev/null || echo 0); [ \"$n\" -gt 0 ] && echo \"claude-setup is $n commit(s) behind origin/main. Run $d/update.sh to catch up.\"; exit 0",
      "timeout": 15,
      "statusMessage": "Checking whether claude-setup is behind"
    }
  ]
}
```

### plan-gate plugin (self-review before any plan)

`/self-review` records a marker file under `~/.claude/plan-reviews/` when a plan review completes. The plan-gate hook denies `ExitPlanMode` unless a marker exists for the current project and is under two hours old, then consumes it, so every new plan needs a fresh review. It ships as a plugin, so there is no hook JSON to paste. Full description: [plugins/plan-gate/README.md](plugins/plan-gate/README.md).

```
/plugin install plan-gate@claude-setup
```

Requires `jq`. The marker is keyed on a hash of the project directory, so one review unlocks one plan in one project.

**Remove any hand-pasted `ExitPlanMode` entry from `hooks.PreToolUse` in `~/.claude/settings.json` first.** Earlier versions of this file told you to paste the gate in by hand. If both run, the first one consumes the marker and the second one denies, so plan mode locks.

### new-day plugin (daily login nudge)

Until the `daily-auth` skill has written today's date to `~/.claude/daily-auth-last-run.json`, a UserPromptSubmit hook adds a note to every human prompt telling Claude to run it first. It skips task notifications, loop ticks, scheduled tasks and messages from other sessions. Full description: [plugins/new-day/README.md](plugins/new-day/README.md).

```
/plugin install new-day@claude-setup
```

Requires `jq` (without it the hook stays silent). Needs `~/.claude/auth-checks.json`, see the `daily-auth` checklist in section 3.

And install the plugins you use via `/plugin` (at minimum, your tracker's plugin for `/start-ticket`).

## 5. Sanity check

Open Claude Code anywhere and run `/pr`, `/babysit-pr`, `/self-review`, or `/start-ticket` - they should appear in the slash-command list. `/output-style` should list Direct, Momentum, and TLDR. `worktree help` and `query_db` with no args should both print usage.

For the plugins, open a fresh session and check:

- `/plugin list` shows `model-discipline`, `plan-gate` and `new-day` enabled, and the session's context includes the model-discipline rules block.
- On a session running the expensive model, an `Agent` dispatch with no `model` is denied with the guard's message; `model: "sonnet"` goes through.
- `bash plugins/model-discipline/tests/agent-model-guard.test.sh` prints `5/5 passed.`
- `bash plugins/model-discipline/tests/agent-rules-append.test.sh` prints `6/6 passed.`
- `ExitPlanMode` without a review is denied with the plan-gate message; after `/self-review` it goes through once.
- `bash plugins/plan-gate/tests/plan-gate.test.sh` prints `6/6 passed.`
- `bash plugins/new-day/tests/new-day-check.test.sh` prints `9/9 passed.`
- `python3 -m pytest bin/tests/test_tidy.py` passes (or `python3 -m unittest bin/tests/test_tidy.py` without pytest).

If you set this repo up before the plugin existed, delete the leftover `~/bin/agent-model-guard` symlink by hand - `install.sh` no longer creates it, but it also never removes links it has stopped iterating over.
