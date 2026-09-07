# claude-setup

My personal [Claude Code](https://claude.com/claude-code) setup, kept in one repo so it is portable to any machine: slash commands, a writing skill, output styles, helper scripts, a PreToolUse hook, and a generic user-level `CLAUDE.md`. Everything here is generic - machine-, employer-, and person-specific values are marked `FILL IN` rather than baked in, so it is meant to be cloned and adapted, not used verbatim.

**To set up a new machine, follow [SETUP.md](SETUP.md).** It covers prerequisites, the install script, and every `FILL IN` in order.

## Install

```bash
git clone git@github.com:zackcpetersen/claude-setup.git
cd claude-setup
./install.sh
```

`install.sh` symlinks the commands, skills, output styles, and `bin/` scripts into `~/.claude` and `~/bin`, so an edit made on any machine lands in this repo's working tree and is one commit away from being backed up. The starter `CLAUDE.md` is copied rather than linked, because it gets personalized per machine, and an existing one is never overwritten. Re-running the script is safe: existing regular files are moved aside to `<name>.bak` first.

## Slash commands (`commands/`)

Installed to `~/.claude/commands/`, available in every project.

- **`/pr`** - Commits the current work with a `[TICKET] type: description` message, pushes the branch, and opens a pull request filled out from the repo's `.github/pull_request_template.md`. It then polls CI and does not hand back control until the checks have settled, escalating to `/babysit-pr` on failure. It never merges on its own.
- **`/babysit-pr`** - Scans all of your open PRs, works out what is blocking each one (failing CI, unresolved review comments including bot reviews, merge conflicts, a stale branch), and fixes what it safely can. Its central rule is to wait for every required check to reach a terminal state before pushing a fix, since each push restarts CI from zero. It asks before merging or force-pushing.
- **`/self-review`** - Dispatches a fresh subagent to review a plan or an implementation against correctness, existing patterns, simplification, duplication, scope, tradeoffs, and reversibility. The subagent has not seen the conversation, so it is not biased toward the work it is reviewing. It reports only problems.
- **`/start-ticket`** - Takes a ticket number, pulls the ticket's description and acceptance criteria from your issue tracker's MCP tools, explores the codebase, and produces an implementation plan with a test strategy before presenting it for approval.

## Skill (`skills/`)

Installed to `~/.claude/skills/`.

- **`write-as-zack`** - Writing-voice rules for drafting Slack messages, emails, PR descriptions, and docs meant for humans. The rules in the file are complete on their own; it can also fetch a live voice page over the Notion MCP tool first, if you point `<YOUR_VOICE_PAGE_URL>` at one. The rules describe my voice, so fork them to describe yours.

## Output styles (`output-styles/`)

Installed to `~/.claude/output-styles/`, switched with `/output-style`.

- **Direct** - Answer first, plain english, steps over paragraphs, one clear recommendation, no hedging or filler. Warm rather than curt.
- **Momentum** - Direct plus explicit progress tracking, real time estimates instead of vague ones, and exactly one concrete next action at the end of every response.
- **TLDR** - One to three sentences by default. Expands only when you ask for more.

## Helper scripts (`bin/`)

Symlinked into `~/bin`, so keep `~/bin` on your `PATH`.

- **`query_db`** - Read-only Postgres queries: `query_db <env-file> "<sql>"`. Credentials are supplied per repo through a gitignored `.env.db.<env>` file rather than being stored here, and every query runs with `default_transaction_read_only=on`, so writes fail rather than needing to be trusted not to happen.
- **`worktree`** - Git worktree manager across several repos, driven by a machine-local `.worktree-config.json` (start from [bin/worktree-config.example.json](bin/worktree-config.example.json)). It creates and removes worktrees, copies the untracked files a fresh checkout needs (env files, `.mcp.json`, `.claude/`), runs your dependency install, and can clean up worktrees whose tickets are done once you supply a `ticket-status` helper for your tracker.
- **`agent-model-guard`** - A PreToolUse hook for the Agent tool. On sessions running an expensive model, it denies subagent dispatches that omit `model` when the agent's own definition has no `model:` pin, because an unpinned dispatch silently inherits the expensive session model. It fails open on every error path, so it cannot break dispatching. The hook only runs once you wire it into `hooks.PreToolUse` in `~/.claude/settings.json`; the snippet is in [SETUP.md](SETUP.md).

## Templates (`claude-md/`)

- **`CLAUDE.md`** - A starter user-level `CLAUDE.md` copied to `~/.claude/CLAUDE.md` on install: general working preferences, communication style, model discipline, git rules, and `FILL IN` sections for your own tools and repo conventions.
- **`MANIFESTO.md`** - "The Ten Laws", a design-philosophy doc to drop into any repo where coding agents do real work. `CLAUDE.md` tells an agent what to do; this tells it how to think when no rule covers the situation. Every law has a `FILL IN` block for a concrete example from the repo you drop it into, because agents imitate examples better than prose.

## A note on settings

`~/.claude/settings.json` is deliberately not in this repo. It can hold secrets in its `env` block, and its hook wiring is machine-local. [SETUP.md](SETUP.md) lists the pieces worth recreating by hand.

## License

MIT. See [LICENSE](LICENSE).
