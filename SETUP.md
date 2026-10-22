# Setup on a New Machine

Everything in this repo is generic - nothing references a specific company, repo, or tracker. Commands are fully generic and read machine-specific values from `~/.claude/CLAUDE.md`. `FILL IN` markers remain only in `claude-md/` and `bin/worktree`. This file walks through all of them.

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
| `output-styles/direct.md` | "Direct" output style - answer first, plain english, no hedging | `~/.claude/output-styles/` (symlink) |
| `output-styles/momentum.md` | "Momentum" output style - Direct plus progress tracking and one next action | `~/.claude/output-styles/` (symlink) |
| `output-styles/tldr.md` | "TLDR" output style - 1-3 sentences, expands only on request | `~/.claude/output-styles/` (symlink) |
| `bin/query_db` | Read-only Postgres query helper | `~/bin/` (symlink) |
| `bin/worktree` | Multi-repo git worktree manager | `~/bin/` (symlink) |
| `bin/worktree-config.example.json` | Starter config for `worktree` | copy + edit, see below |
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

- 2026-10-22: Several changes, each needs a step:
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
- No file edits. The optional voice page URL lives in the `### Writing voice` section of `~/.claude/CLAUDE.md`; delete that bullet to run on the rules written into the skill, which are complete on their own. The rules are Zack's; edit them to describe your own voice.

### `skills/board/SKILL.md`
- No file edits. Everything machine-specific lives in the `### Work board` section of `~/.claude/CLAUDE.md`; copy that block from `claude-md/CLAUDE.md.template` and fill it in. The skill stops with a clear message if the section is missing.
- Create one empty Notion page with an inline database (any name, only the default title property) and put its URL on the `Board page` line. The skill adds the columns it needs on first run.
- Optional: add the `Projects data source` line. On the first run the skill creates a "Projects" database under the board page with the schema in `page-template.md` and gives you the `collection://` id to paste back; after that it keeps one page per workstream current.
- Needs the Notion MCP plugin, the Slack MCP plugin, your tracker's MCP plugin, `gh`, and `~/bin/worktree` with its config. The ticket flow also needs `/start-ticket`, `/self-review`, `/pr` and the built-in `/code-review` skill.
- Optional: the `/watch-slack` state file path, if you run that command; leave the line out otherwise.

### `skills/review-pr/SKILL.md`
- No file edits. Needs `gh` and the built-in `/code-review` skill. Uses the writing-voice skill named in the `### Writing voice` section of `~/.claude/CLAUDE.md` when present, otherwise the voice rules written into `dispatch-prompt.md`.

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

If you set this repo up before the plugin existed, delete the leftover `~/bin/agent-model-guard` symlink by hand - `install.sh` no longer creates it, but it also never removes links it has stopped iterating over.
