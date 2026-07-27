# Setup on a New Machine

Everything in this repo is generic - nothing references a specific company, repo, or tracker. Anywhere something machine- or employer-specific is needed, it's marked `FILL IN`. This file walks through all of them.

## What's in here

| Path | What it is | Installed to |
|---|---|---|
| `commands/pr.md` | `/pr` - commit, create PR, babysit CI until green | `~/.claude/commands/` (symlink) |
| `commands/babysit-pr.md` | `/babysit-pr` - unblock all open PRs (CI, comments, conflicts) | `~/.claude/commands/` (symlink) |
| `commands/self-review.md` | `/self-review` - subagent review of a plan or implementation | `~/.claude/commands/` (symlink) |
| `commands/start-ticket.md` | `/start-ticket` - fetch ticket, produce implementation plan | `~/.claude/commands/` (symlink) |
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
- Database names/envs for the query_db section
- Any other machine-specific tools (log search, tracker MCP, etc.)
- The Repo Conventions table (one row per repo: default branch, test command, lint command)

### `commands/pr.md`
- One `FILL IN`: the ticket tracker base URL used in PR descriptions (search for `YOUR_TRACKER_BASE_URL`).

### `commands/start-ticket.md`
- Needs your issue tracker's MCP tools available (e.g. install the Atlassian plugin for Jira, or your tracker's equivalent). No file edits required.

### `bin/query_db`
- Edit the `DBS` and `ENVS` arrays at the top of the script.
- For each db/env pair, create `~/bin/env_files/.env.<db>.<env>` with `DATABASE_HOST`, `DATABASE_PORT` (optional), `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`.
- **Never commit `env_files` anywhere** - they are credentials. They live outside this repo by design.

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

And install the plugins you use via `/plugin` (at minimum, your tracker's plugin for `/start-ticket`).

## 5. Sanity check

Open Claude Code anywhere and run `/pr`, `/babysit-pr`, `/self-review`, or `/start-ticket` - they should appear in the slash-command list. `worktree help` and `query_db` with no args should both print usage.
