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

- **`write-as-zack`** - Writing-voice rules for drafting Slack messages, emails, PR descriptions, and docs meant for humans. The rules in the file are complete on their own; it can also fetch a live voice page over the Notion MCP tool first, if `~/.claude/config/writing-voice.md` names one in a `### Writing voice` section. The rules describe my voice, so fork them to describe yours.
- **`board`** - A daily work board in Notion: one row per day with a human-readable "Your view" (needs you, in flight, blocked, pacing, done) and a Claude scratchpad child page. `/board` rebuilds it from the issue tracker, GitHub, Slack, local worktrees, memory and other Claude sessions via read-only sub-agents; `/board rollover` also writes a standup at the top of the new day (grouped by project: what got done, what went live, what is next and who you are waiting on, plus oncall work you logged with `/board done oncall:`); `/board start <TICKET>` runs the worktree -> plan -> approve -> implement -> review -> `/pr` flow in background agents. Every machine-specific value (the Notion page, Slack ids, tracker project, repos) comes from `~/.claude/config/board.md`; point it at any empty Notion page and it creates the schema. Optionally add a `Projects data source` line and the board keeps one private page per workstream (where we are, decisions, dated progress log), linked from each day's row.
- **`reviewing-prs`** - The rules for anything said on a pull request, in either direction: triage (high blocks, medium is a `nit:`, low is dropped unless it is a one-line fix), verdict, comment style, posting (one review, inline only, list shown first), and etiquette for your own PRs (manual validation before a review ask, one-line `PR for <what it does>` asks, short thankful replies, merge only when approved and green). `review-pr` and `pr` read it first.
- **`daily-auth`** - Checks every login and credential the day needs (cloud SSO, `gh`, SSH, VPN, database env files, MCP servers, browser consoles) from a per-machine `~/.claude/auth-checks.json`, runs each fix right away (the user approves prompts and finishes browser steps), lists only what is left for the user, and records the day's results so the `new-day` plugin goes quiet. Board rollover runs it too.
- **`sync-repos`** - Fast-forwards every repo listed in `~/.claude/sync-repos.json` to `origin/main`, switches off branches whose PR merged when the tree is clean, and flags lock file changes, new migrations, dirty trees and failed fast-forwards. It never rebases, resets or drops local work.
- **`review-pr`** - Reviews a teammate's pull request: `/review-pr <number or URL>` runs the built-in `/code-review` in a background opus agent, triages the findings (high blocks, medium becomes a `nit:`, low is dropped), drafts every comment as a question or a suggestion in your writing voice, shows you the list for per-comment approval, then posts one GitHub review with inline comments only, no summary comment unless the comments need one (approve when nothing blocks, otherwise comment). Nothing is posted until you say yes.
- **`project-status`** - A visual status dashboard for your projects, published as a private Artifact: a nav rail and a tile grid; a home view with today's numbers (need you, due today, late, done today), KPI tiles with sparklines, throughput, project progress bars, a three-week timeline, the top of your inbox, your PR pipeline and who you are waiting on; a `#stats` page with turnaround and repo-group splits; an inbox page that ranks everything waiting on you (project asks, nudges, your GitHub PRs and review requests, Slack asks held for later, session items) with effort chips; one page per project (needed from you, where it stands, full breakdown); a page of people you are waiting on; and a list of other items. `build.py` turns a JSON data file into the page; names, links and colors come from `~/.claude/project-status/config.json`, so the template stays generic. `add_oneoff.py` adds a standalone item in one line, and `job.py` records progress on a long job. Every ticket, PR or thread the page names links to its source.
- **`watch`** - Waits that cost nothing while idle. Each wait is one background command (`wait-for`) that polls a PR, a deploy or a Dagster run and wakes the session once, on an event. A Slack poll (`wait-for slack`) checks every 5 minutes on the cheapest model, for about half a cent, and wakes the session only when someone messaged you; the session then skips what does not need you, and for what does, runs the read-only checks first and asks you one informed question. Nothing is watched without a yes, and a merge happens only on your per-PR approval, pinned to the head commit you approved. Every machine-specific value comes from `~/.claude/config/watch.md`.

- **`tidy`** - Cleanup on a schedule. At board wrap it removes what is provably dead (worktrees and branches proven merged, finished processes and agents, empty files); at rollover it flags old board lines and local items; once a week it does a deep clean with one question per category for anything that would lose content. Files are archived, never deleted, and every action is logged with its undo command. A catch-all "Loose ends" list, capped and aged, holds things with no other home. Values come from `~/.claude/config/tidy.md`.

## Output styles (`output-styles/`)

Installed to `~/.claude/output-styles/`, switched with `/output-style`.

- **Direct** - Answer first, plain english, steps over paragraphs, one clear recommendation, no hedging or filler. Warm rather than curt.
- **Momentum** - Direct plus explicit progress tracking, real time estimates instead of vague ones, and exactly one concrete next action at the end of every response.
- **TLDR** - One to three sentences by default. Expands only when you ask for more.

## Helper scripts (`bin/`)

Symlinked into `~/bin`, so keep `~/bin` on your `PATH`.

- **`query_db`** - Read-only Postgres queries: `query_db <env-file> "<sql>"`. Credentials are supplied per repo through a gitignored `.env.db.<env>` file rather than being stored here, and every query runs with `default_transaction_read_only=on`, so writes fail rather than needing to be trusted not to happen.
- **`worktree`** - Git worktree manager across several repos, driven by a machine-local `.worktree-config.json` (start from [bin/worktree-config.example.json](bin/worktree-config.example.json)). It creates and removes worktrees, copies the untracked files a fresh checkout needs (env files, `.mcp.json`, `.claude/`), runs your dependency install, and can clean up worktrees whose tickets are done once you supply a `ticket-status` helper for your tracker.
- **`wait-for`** - The script the `watch` skill starts in the background: `pr`, `deploy`, `dagster` and `slack` modes that poll, print one event line and exit. `slack` reads Slack through a headless Claude run limited to the Slack read tools. Python 3 standard library only, with `unittest` tests in `bin/tests/`.
- **`tidy`** - The script the `tidy` skill runs: `tidy scan --mode daily|stale|weekly` lists leftovers by tier (read-only except `git fetch --prune`; `--no-fetch` skips that), and `tidy apply` acts only on the findings piped to it as a list (Tier 2 ones only when marked `"approved": true`), re-checking each one live first, logging its undo command before it acts, and keeping unmerged commits under `refs/tidy-archive/` before a branch is deleted. Python 3 standard library only, with `unittest` tests in `bin/tests/test_tidy.py` that use temp repos only.
- **`pr-precheck`** - Run once before the first push: `pr-precheck fix` lints the changed files with autocorrect and runs only the tests tied to them, and skips the run when this exact tree already passed. `pr-precheck report` is read-only and lists the diff size, generated files that look stale and outside calls made inside a lock, for the reviewer. `pr-precheck hook` is a check-only pre-push hook that fails open. Per-repo overrides live in `~/.claude/config/pr-precheck.json`. Python 3 standard library only, with `unittest` tests in `bin/tests/test_pr_precheck.py`.
- **`status-feeds`** - Refreshes the status page's inbox data with no model in the loop: `status-feeds run` reads your open PRs and review requests from GitHub (one GraphQL call through `gh`) and the Slack poll's triage log, and writes `feeds/github.json` and `feeds/slack.json` under `~/.claude/project-status/`. `doctor` checks the setup; `schedule --print launchd|cron` prints a schedule for you to install. Python 3 standard library only, with `unittest` tests in `bin/tests/test_status_feeds.py`.
- **`eng-stats`** - Pull-request stats for the status page, no model in the loop: `eng-stats run` caches the org's PRs from GitHub (paged GraphQL search through `gh`, incremental after the first fill) and writes `feeds/stats.json` with aggregates for you and your team (PRs merged, reviews given and received, time to first review and to merge, weekly series). No per-person rows, no PR titles. `doctor` checks the setup; `schedule --print launchd|cron` prints a daily schedule for you to install. Tests in `bin/tests/test_eng_stats.py`.
- **`agent-model-guard`** - No longer symlinked from here. It ships as part of the `model-discipline` plugin; see [Plugins (`plugins/`)](#plugins-plugins) below.

## Plugins (`plugins/`)

- **`model-discipline`** - Keeps expensive-model spend on judgment work. It bundles the `agent-model-guard` PreToolUse hook (denies subagent dispatches that omit `model` on an expensive session when the agent definition has no pin), an `agent-rules-append` hook that adds the sub-agent rules (own env, one push, report once and never also by SendMessage, one owner per file) to write-capable dispatch prompts, a `context-warn` hook that tells the main session once when its context passes 150k tokens, a `review-target-guard` hook that denies `/code-review` with a bare PR number, a short rules block injected at session start, and a `playbook` skill with the full dispatch-and-session reference. Installed with `/plugin install model-discipline@claude-setup` rather than by `install.sh`. Full description: [plugins/model-discipline/README.md](plugins/model-discipline/README.md).
- **`plan-gate`** - Blocks `ExitPlanMode` until `/self-review` has recorded a pass for the current project in the last two hours, then consumes that pass so every new plan needs a fresh review. Installed with `/plugin install plan-gate@claude-setup`. Full description: [plugins/plan-gate/README.md](plugins/plan-gate/README.md).
- **`new-day`** - Until the `daily-auth` skill has run today, adds a note to every human prompt telling Claude to run it first, so logins get checked even in a session left open overnight. Installed with `/plugin install new-day@claude-setup`. Full description: [plugins/new-day/README.md](plugins/new-day/README.md).

## Templates (`claude-md/` and `config/`)

- **`CLAUDE.md`** - A starter user-level `CLAUDE.md` copied to `~/.claude/CLAUDE.md` on install: general working preferences, communication style, model discipline, git rules, and `FILL IN` sections for your own tools and repo conventions.
- **`config/*.example.*`** - Per-skill config (board, watch, tidy, writing voice, plus optional self-review checks and pr-precheck overrides). `install.sh` copies the four `.md` files to `~/.claude/config/` only on a fresh install (never on an update, so a skill you turned off stays off); each skill reads only its own file.
- **`MANIFESTO.md`** - "The Ten Laws", a design-philosophy doc to drop into any repo where coding agents do real work. `CLAUDE.md` tells an agent what to do; this tells it how to think when no rule covers the situation. Every law has a `FILL IN` block for a concrete example from the repo you drop it into, because agents imitate examples better than prose.

## A note on settings

`~/.claude/settings.json` is deliberately not in this repo. It can hold secrets in its `env` block, and values like the session model are machine-local. The model-discipline and plan-gate hooks come from plugins, so nothing needs pasting for those. [SETUP.md](SETUP.md) lists the pieces worth recreating by hand.

## License

MIT. See [LICENSE](LICENSE).
