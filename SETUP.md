# Setup on a New Machine

Everything in this repo is generic - nothing references a specific company, repo, or tracker. Anywhere something machine- or employer-specific is needed, it's marked `FILL IN`. This file walks through all of them.

## What's in here

| Path | What it is | Installed to |
|---|---|---|
| `commands/pr.md` | `/pr` - commit, create PR, babysit CI until green | `~/.claude/commands/` (symlink) |
| `commands/babysit-pr.md` | `/babysit-pr` - unblock all open PRs (CI, comments, conflicts) | `~/.claude/commands/` (symlink) |
| `commands/self-review.md` | `/self-review` - subagent review of a plan or implementation | `~/.claude/commands/` (symlink) |
| `commands/start-ticket.md` | `/start-ticket` - fetch ticket, produce implementation plan | `~/.claude/commands/` (symlink) |
| `skills/write-as-zack/` | `write-as-zack` skill - writing-voice rules, with an optional live voice page | `~/.claude/skills/` (symlink) |
| `output-styles/direct.md` | "Direct" output style - answer first, plain english, no hedging | `~/.claude/output-styles/` (symlink) |
| `output-styles/momentum.md` | "Momentum" output style - Direct plus progress tracking and one next action | `~/.claude/output-styles/` (symlink) |
| `output-styles/tldr.md` | "TLDR" output style - 1-3 sentences, expands only on request | `~/.claude/output-styles/` (symlink) |
| `bin/query_db` | Read-only Postgres query helper | `~/bin/` (symlink) |
| `bin/worktree` | Multi-repo git worktree manager | `~/bin/` (symlink) |
| `bin/worktree-config.example.json` | Starter config for `worktree` | copy + edit, see below |
| `claude-md/CLAUDE.md` | Generic user-level Claude Code preferences | copied to `~/.claude/CLAUDE.md` if absent |
| `install.sh` | Does the linking/copying above | - |

Symlinks mean edits made on any machine land in this repo's working tree - commit and push to back them up.

## 1. Prerequisites

- Claude Code installed and logged in
- `gh` CLI installed and authenticated (`gh auth login`) - needed by `/pr` and `/babysit-pr`
- `jq` - needed by `worktree`
- `psql` - needed by `query_db`
- Make sure `~/bin` is on your `PATH`

## 2. Install

```bash
git clone git@github.com:zackcpetersen/claude-setup.git
cd claude-setup
./install.sh
```

## 3. Fill-in checklist

Work through these once per machine:

### `~/.claude/CLAUDE.md`
`install.sh` copies the starter file only if you don't already have one. Open it and fill in every `FILL IN` comment:
- Per-repo notes for the query_db section (which `.env.db.*` files exist, which envs are production)
- Any other machine-specific tools (log search, tracker MCP, etc.)
- The Repo Conventions table (one row per repo: default branch, test command, lint command)

### `commands/pr.md`
- One `FILL IN`: the ticket tracker base URL used in PR descriptions (search for `YOUR_TRACKER_BASE_URL`).

### `commands/start-ticket.md`
- Needs your issue tracker's MCP tools available (e.g. install the Atlassian plugin for Jira, or your tracker's equivalent). No file edits required.

### `skills/write-as-zack/SKILL.md`
- One `FILL IN`: `<YOUR_VOICE_PAGE_URL>`, an optional link to a voice guide the skill fetches with the Notion MCP tool before drafting. Leave the placeholder alone to run on the rules written into the skill, which are complete on their own. The rules are Zack's; edit them to describe your own voice.

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

### agent-model-guard hook (model discipline)

`bin/agent-model-guard` (symlinked to `~/bin` by install.sh) denies Agent dispatches that omit `model` on Fable sessions when the agent definition has no `model:` pin - unpinned dispatches silently inherit the expensive session model. The hook wiring is machine-local; add it to `hooks.PreToolUse` in `~/.claude/settings.json`:

```json
{
  "matcher": "Agent|Task",
  "hooks": [
    {
      "type": "command",
      "command": "bash \"$HOME/bin/agent-model-guard\"",
      "timeout": 15,
      "statusMessage": "Checking subagent model discipline"
    }
  ]
}
```

Without this snippet the guard script exists but never runs.

And install the plugins you use via `/plugin` (at minimum, your tracker's plugin for `/start-ticket`).

## 5. Sanity check

Open Claude Code anywhere and run `/pr`, `/babysit-pr`, `/self-review`, or `/start-ticket` - they should appear in the slash-command list. `/output-style` should list Direct, Momentum, and TLDR. `worktree help` and `query_db` with no args should both print usage.
