# claude-setup

My personal [Claude Code](https://claude.com/claude-code) setup, kept in one repo so it is portable to any machine: slash commands, a writing skill, output styles, helper scripts, plugins, and a generic user-level `CLAUDE.md`. Everything here is generic - machine-, employer-, and person-specific values are marked `FILL IN` rather than baked in, so it is meant to be cloned and adapted, not used verbatim.

**To set up a new machine, follow [SETUP.md](SETUP.md).** It covers prerequisites, the install script, and every `FILL IN` in order. Already set up? Run `./update.sh` - it pulls, relinks, and prints what needs a manual step (see "Updating an existing machine" in SETUP.md).

## Install

```bash
git clone git@github.com:zackcpetersen/claude-setup.git
cd claude-setup
./install.sh
```

`install.sh` symlinks the commands, skills, output styles, and `bin/` scripts into `~/.claude` and `~/bin`, so an edit made on any machine lands in this repo's working tree and is one commit away from being backed up. The starter `CLAUDE.md` is copied rather than linked, because it gets personalized per machine, and an existing one is never overwritten. Re-running the script is safe: existing regular files are moved aside to `<name>.bak` first.

## Slash commands (`commands/`)

Installed to `~/.claude/commands/`, available in every project.

- **`/pr`** - Commits the current work using the commit message format from your `~/.claude/CLAUDE.md`, pushes the branch, and opens a pull request filled out from the repo's `.github/pull_request_template.md`. It then runs a self code review of the PR (the built-in `/code-review` skill in a background opus agent, `--review-effort` to change the level) while polling CI, and hands CI failures and review findings to `/babysit-pr` together for one approval and one push. It never merges on its own.
- **`/babysit-pr`** - Scans all of your open PRs, works out what is blocking each one (failing CI, unresolved review comments including bot reviews, merge conflicts, a stale branch), and fixes what it safely can. Its central rule is to wait for every required check to reach a terminal state before pushing a fix, since each push restarts CI from zero. It asks before merging or force-pushing.
- **`/self-review`** - Dispatches a fresh subagent to review a plan or an implementation against correctness, existing patterns, simplification, duplication, scope, tradeoffs, and reversibility. The subagent has not seen the conversation, so it is not biased toward the work it is reviewing. It reports only problems.
- **`/start-ticket`** - Takes a ticket number, pulls the ticket's description and acceptance criteria from your issue tracker's MCP tools, explores the codebase, and produces an implementation plan with a test strategy before presenting it for approval.

## Skill (`skills/`)

Installed to `~/.claude/skills/`.

- **`write-as-zack`** - Writing-voice rules for drafting Slack messages, emails, PR descriptions, and docs meant for humans. The rules in the file are complete on their own; it can also fetch a live voice page over the Notion MCP tool first, if your `~/.claude/CLAUDE.md` names one in a `### Writing voice` section. The rules describe my voice, so fork them to describe yours.
- **`board`** - A daily work board in Notion: one row per day with a human-readable "Your view" (needs you, in flight, blocked, pacing, done) and a Claude scratchpad child page. `/board` rebuilds it from the issue tracker, GitHub, Slack, local worktrees, memory and other Claude sessions via read-only sub-agents; `/board rollover` also writes a standup at the top of the new day (grouped by project: what got done, what went live, what is next and who you are waiting on, plus oncall work you logged with `/board done oncall:`); `/board start <TICKET>` runs the worktree -> plan -> approve -> implement -> review -> `/pr` flow in background agents. Every machine-specific value (the Notion page, Slack ids, tracker project, repos) comes from the `### Work board` section of `~/.claude/CLAUDE.md`; point it at any empty Notion page and it creates the schema. Optionally add a `Projects data source` line and the board keeps one private page per workstream (where we are, decisions, dated progress log), linked from each day's row.
- **`reviewing-prs`** - The rules for anything said on a pull request, in either direction: triage (high blocks, medium is a `nit:`, low is dropped unless it is a one-line fix), verdict, comment style, posting (one review, inline only, list shown first), and etiquette for your own PRs (manual validation before a review ask, link-plus-one-sentence asks, short thankful replies, merge only when approved and green). `review-pr` and `pr` read it first.
- **`daily-auth`** - Checks every login and credential the day needs (cloud SSO, `gh`, SSH, VPN, database env files, MCP servers, browser consoles) from a per-machine `~/.claude/auth-checks.json`, runs each fix right away (the user approves prompts and finishes browser steps), lists only what is left for the user, and records the day's results so the `new-day` plugin goes quiet. Board rollover runs it too.
- **`sync-repos`** - Fast-forwards every repo listed in `~/.claude/sync-repos.json` to `origin/main`, switches off branches whose PR merged when the tree is clean, and flags lock file changes, new migrations, dirty trees and failed fast-forwards. It never rebases, resets or drops local work.
- **`review-pr`** - Reviews a teammate's pull request: `/review-pr <number or URL>` runs the built-in `/code-review` in a background opus agent, triages the findings (high blocks, medium becomes a `nit:`, low is dropped), drafts every comment as a question or a suggestion in your writing voice, shows you the list for per-comment approval, then posts one GitHub review with inline comments only, no summary comment unless you ask for one (approve when nothing blocks, otherwise comment). Nothing is posted until you say yes.
- **`watch`** - A registry of things you are waiting on: a reply on a Slack or email thread, a PR going green, a deploy reaching prod, a Dagster run finishing. Each wait is checked cheaply on its own cadence (a script with no model where a command line can see it, a small model where only a connector can), handled inside bounds you approved (read-only verification, drafts, pre-approved merges), and raised only when a person has to act. A silent tick costs one shell call. Every machine-specific value comes from the `### Watches` section of `~/.claude/CLAUDE.md`.

## Output styles (`output-styles/`)

Installed to `~/.claude/output-styles/`, switched with `/output-style`.

- **Direct** - Answer first, plain english, steps over paragraphs, one clear recommendation, no hedging or filler. Warm rather than curt.
- **Momentum** - Direct plus explicit progress tracking, real time estimates instead of vague ones, and exactly one concrete next action at the end of every response.
- **TLDR** - One to three sentences by default. Expands only when you ask for more.

## Helper scripts (`bin/`)

Symlinked into `~/bin`, so keep `~/bin` on your `PATH`.

- **`query_db`** - Read-only Postgres queries: `query_db <env-file> "<sql>"`. Credentials are supplied per repo through a gitignored `.env.db.<env>` file rather than being stored here, and every query runs with `default_transaction_read_only=on`, so writes fail rather than needing to be trusted not to happen.
- **`worktree`** - Git worktree manager across several repos, driven by a machine-local `.worktree-config.json` (start from [bin/worktree-config.example.json](bin/worktree-config.example.json)). It creates and removes worktrees, copies the untracked files a fresh checkout needs (env files, `.mcp.json`, `.claude/`), runs your dependency install, and can clean up worktrees whose tickets are done once you supply a `ticket-status` helper for your tracker.
- **`watch`** - The registry script the `watch` skill drives: it owns the registry file and its lock, quiet hours and business-day expiry, and the PR, deploy and Dagster checks. Python 3 standard library only, with `unittest` tests in `bin/tests/`.
- **`agent-model-guard`** - No longer symlinked from here. It ships as part of the `model-discipline` plugin; see [Plugins (`plugins/`)](#plugins-plugins) below.

## Plugins (`plugins/`)

- **`model-discipline`** - Keeps expensive-model spend on judgment work. It bundles the `agent-model-guard` PreToolUse hook (denies subagent dispatches that omit `model` on an expensive session when the agent definition has no pin), an `agent-rules-append` hook that adds the sub-agent rules (own env, one push, report once, one owner per file) to write-capable dispatch prompts, a short rules block injected at session start, and a `playbook` skill with the full dispatch-and-session reference. Installed with `/plugin install model-discipline@claude-setup` rather than by `install.sh`. Full description: [plugins/model-discipline/README.md](plugins/model-discipline/README.md).
- **`plan-gate`** - Blocks `ExitPlanMode` until `/self-review` has recorded a pass for the current project in the last two hours, then consumes that pass so every new plan needs a fresh review. Installed with `/plugin install plan-gate@claude-setup`. Full description: [plugins/plan-gate/README.md](plugins/plan-gate/README.md).
- **`new-day`** - Until the `daily-auth` skill has run today, adds a note to every human prompt telling Claude to run it first, so logins get checked even in a session left open overnight. Installed with `/plugin install new-day@claude-setup`. Full description: [plugins/new-day/README.md](plugins/new-day/README.md).

## Templates (`claude-md/`)

- **`CLAUDE.md`** - A starter user-level `CLAUDE.md` copied to `~/.claude/CLAUDE.md` on install: general working preferences, communication style, model discipline, git rules, and `FILL IN` sections for your own tools and repo conventions.
- **`MANIFESTO.md`** - "The Ten Laws", a design-philosophy doc to drop into any repo where coding agents do real work. `CLAUDE.md` tells an agent what to do; this tells it how to think when no rule covers the situation. Every law has a `FILL IN` block for a concrete example from the repo you drop it into, because agents imitate examples better than prose.

## A note on settings

`~/.claude/settings.json` is deliberately not in this repo. It can hold secrets in its `env` block, and values like the session model are machine-local. The model-discipline and plan-gate hooks come from plugins, so nothing needs pasting for those. [SETUP.md](SETUP.md) lists the pieces worth recreating by hand.

## License

MIT. See [LICENSE](LICENSE).
