Superseded by docs/superpowers/plans/2026-10-31-watch-simple.md (2026-10-31).

# Watch: a registry of things we are waiting on

Design, 2026-10-28. Status: approved by the user 2026-10-28 (with the silent no-op tick rule). Lives in claude-setup as a generic skill; every machine-specific value goes in a `### Watches` config section of `~/.claude/CLAUDE.md`, the same way the `board` skill works.

## Intent

A working day has a lot of "wait for X, then do Y": a reply to a Slack thread, an answer on an email thread, a PR going green, a deploy reaching prod so a change can be verified, a Dagster run finishing. Today those waits are either polled by hand from the master session (expensive, and the user has to remember) or missed. The `watch` skill makes each wait a registered row that is checked on its own cadence by the cheapest means available, handled automatically inside approved bounds, and raised to the user only when a person has to act.

## Goals

- One registry of open waits that outlives sessions and `/clear`, re-armed at board rollover.
- Each check runs as cheaply as its kind allows: a shell poll with no model when a command line exists, a haiku agent when only a connector can read it, sonnet only when a reply has to be judged against an expectation.
- Watches get created without the user asking: from a plain-English line in chat, and automatically by other skills (the board when a draft is marked sent, `/pr` when a PR opens, rollover for standing watches).
- When a watch fires, the session handles what it may: run read-only verification, draft the reply, update the board and tracker drafts, and merge a PR the user already pre-approved. Everything else is raised with the draft ready.
- Raising is one place: a Needs-you line on today's board row plus a line in chat, and a push notification for urgent items.
- Quiet hours and weekends pause polling unless a watch opts out.

## Non-goals

- Alert and on-call monitoring (observability monitors, error trackers) stays with the on-call skills. A watch is a wait the user created, not a standing alarm.
- No sending. Slack and email stay drafts only; tracker and GitHub posts keep per-item approval. The only write without a prompt is a merge the user pre-approved in chat for that specific PR, recorded on the watch row.
- Not a general task scheduler. A watch has a target and an expected event; "remind me at 3" is not a watch.

## Anti-goals (what would make this a failure)

- A watch that dies silently. Silence must never look like "still waiting": every watch records its last successful check, and a stale one is raised.
- A tick that burns top-model tokens when nothing is due. The no-op path is one shell call and one line.
- A check agent that hangs on a permission prompt (this happened today). Check agents only use pre-allowed read and draft tools; anything else runs in the master.
- Nagging. One raise per event, no repeats until the state changes.
- Clutter. A no-op tick is silent: no chat line, no log line in the registry beyond `last_tick`, no board edit. Progress chatter ("checked 4 watches") never appears; only fired, stale and expired watches produce output.

## Constraints

- Session cron jobs (`CronCreate`) are in-memory, fire only when the session is idle, and expire after 7 days. The registry therefore lives on disk and the tick is re-armed by rollover and by any `/watch` call that finds no job.
- Background agents on this machine have stalled on classifier prompts; the detect and judge agents must need no prompt at all (allow rules below).
- Slack and Gmail are reachable only through MCP connectors, so those checks need an agent. GitHub (`gh`) and Dagster (GraphQL with the token from an env file) are reachable from a script.
- Generic: nothing in the skill names a company, person, channel, repo, ticket or path. Those come from config.
- No em-dashes anywhere. Plain English.

## How it works

### Registry

`~/.claude/watches.json` (path from config), one object per watch, written only by the `bin/watch` script so edits are atomic and validated. Fields:

- `id`: `w-<n>`.
- `kind`: `slack-thread`, `slack-dm`, `email-thread`, `pr`, `deploy`, `dagster-run`, `dagster-backfill`, `requests-channel`.
- `target`: kind-specific keys (channel id and thread ts; mailbox thread id; repo and PR number; repo and deploy rule name; run or backfill id).
- `expect`: one sentence, what counts as the event ("a reply from <user id> that says whether their loader reads every file in the folder"; "all checks green and one approval"; "run reaches a terminal state").
- `every`, `slow_every`: cadence while fresh and after the expiry rule trips. `after`: optional earliest check time.
- `expires`: an absolute time or a rule name from the kinds table.
- `quiet`: `true` respects quiet hours (default), `false` polls through them.
- `urgent`: `true` means a raise also sends a push notification.
- `on_fire`: `verify` (list of read-only shell commands to run when the event lands), `draft` (`reply` or `none`), `merge` (null, or the user's words and time when they pre-approved the merge of this PR), `then` (optional follow-up watch to register, used for "PR merged, now watch the deploy").
- `created`, `created_by` (`chat`, `board`, `pr`, `rollover`, `script`), `board_line` (text of the Needs-you or In-flight line it belongs to).
- `state`: `status` (`armed`, `fired`, `handled`, `raised`, `expired`, `paused`, `stopped`), `cursor` (last seen Slack ts, message id, commit sha, run status), `last_check`, `last_ok_check`, `checks`, `errors`, `note`.

### Tick

One session cron job fires every 5 minutes on an off-minute with the prompt `/watch tick`. The tick:

1. Runs `bin/watch tick` once. The script reads the registry, applies quiet hours and each watch's `every`, `after` and `expires`, runs every due script-backed check itself (`pr`, `deploy`, `dagster-*`), updates cursors and `last_check`, and prints one compact JSON line: watches that fired, watches due for an agent check (grouped by connector), watches gone stale, and watches that just expired. When all four lists are empty the script prints nothing and exits 0, and the tick ends with no chat output at all: no status line, no "nothing due", nothing on the board. The user only sees a tick when it has something to say.
2. Dispatches one haiku detect agent per connector that has due watches (one agent for all due Slack watches, one for Gmail), using the prompts in `dispatch-prompts.md`. The agent reads each thread since its cursor and reports new messages verbatim (author, time, text) or `NONE`, nothing else. The master records cursors and fired watches through the script.
3. For each fired watch whose `expect` needs judgment (any reply watch), dispatches one sonnet judge agent with the expectation, the new messages, the thread so far, and the draft brief. It returns `MET`, `PARTIAL` or `NOT MET` with one line of reasoning and, when `on_fire.draft` is `reply`, creates the draft and returns its id. The judge may create drafts and nothing else.
4. The master handles each fired watch: runs `verify` commands and reads the output, merges when `on_fire.merge` is set and the PR is green and approved, registers the `then` watch, logs any draft in the board's `## Drafts today` table, writes the Needs-you line, says one line in chat, and sends a push when `urgent`. It then marks the watch `handled` or `raised` through the script.
5. Stale watches (no successful check in three cadences, or an agent that did not report within 10 minutes) and expired watches are raised once with the reason.

### Kinds (version one)

| Kind | Check | Default cadence | Expiry rule | On fire default |
|---|---|---|---|---|
| `slack-thread`, `slack-dm` | haiku agent reads the thread or DM since the cursor | 10 min, then 60 min | 1 business day: raise "no reply, nudge?" and switch to `slow_every`; stop at 5 business days | judge, draft the reply, raise with the draft |
| `email-thread` | haiku agent reads the thread since the last message id | 20 min, then 60 min | same as Slack | same as Slack |
| `pr` | script: `gh pr view` state, merge state, review decision, check rollup | 15 min | until merged or closed | raise on failed checks or changes requested; merge when pre-approved, green and approved; otherwise raise "ready to merge?" |
| `deploy` | script: the repo's deploy rule from config (a workflow run on the default branch at or after a sha, a release tag, or the sha reaching a branch) | 30 min | 2 days then raise | run `verify` commands; raise the result, urgent when verification fails |
| `dagster-run`, `dagster-backfill` | script: GraphQL run or backfill status, backfill finished only when every partition is terminal | 5 min | until terminal; raise when running past the expected hours | raise the outcome; failure is urgent |
| `requests-channel` | haiku agent reads the configured channel for new top-level messages from the configured user since the state file ts | 10 min | standing, never expires | the master handles each request per the existing requests-channel rules (research, reply in thread) |

Quiet hours default to the config window plus weekends. Business-day math for expiry uses the same window. A `dagster-*` watch and any watch created with "through the night" sets `quiet: false`.

### Creating watches

- Chat: a line like "watch for Kenneth's reply and draft an answer" or "verify the Amazon change once it deploys" becomes a row. The master picks the kind and defaults, writes the row with `bin/watch add`, and confirms in one line: id, kind, cadence, expiry.
- Board: when a row in `## Drafts today` flips to `sent` and the draft asked something, the board registers a reply watch on that thread with `expect` set to the ask. The Work registry's PR rows register `pr` watches. Rollover runs `/watch arm` (re-creates the cron job, raises anything that expired overnight, registers standing watches such as `requests-channel`, mirrors the registry to the scratchpad as a `## Watches` table). Wrap lists open watches in the handoff and deletes the cron job.
- `/pr`: registers a `pr` watch when the PR opens, with `then` set to a `deploy` watch when the user asked for a prod verification.
- Scripts: any launcher the user runs (like a run-pairs script) can call `bin/watch add` with a run id.

Commands: `/watch` (list, one line per watch with next check), `/watch add <plain English>`, `/watch stop <id>`, `/watch pause` and `/watch resume` (all), `/watch tick` (the cron prompt), `/watch arm`.

### Raising

Needs-you line format: `- [ ] <holder>: <exact ask> (watch <id>, draft <id> when one exists)`. The chat line is the same text. A push notification goes out only for `urgent` watches: verification failed, a Dagster run failed, CI failed on the user's own PR, or a reply the user flagged as blocking today's goal. One raise per state change.

### Permissions

The user adds allow rules (user settings) so detect and judge agents never prompt: the Slack read tools (thread, channel, search), the Gmail read tools (thread, message, search), the Slack draft tool, the Gmail create and update draft tools, `Bash(<path to bin/watch> *)`, `Bash(gh pr view *)`, `Bash(gh run list *)`, `Bash(gh api repos/*)`. The skill's install notes list the exact rule strings. No agent gets a send, post, transition or merge rule; the merge runs in the master.

### Config section (`### Watches` in CLAUDE.md, template in claude-md)

- Registry file path. Tick interval (default 5m). Quiet hours window and weekend flag.
- Requests channel (optional): channel id, user id, state file. Replaces the old `watch-slack` command, whose posting carve-out stays in the user's own CLAUDE.md.
- Dagster (optional): GraphQL URL and env file path with the token variable name. The script never prints the token.
- Deploy rules: one line per repo, `repo: <rule>` where the rule is `workflow <name> on <branch>`, `release-tag`, or `branch <name>`.
- Business hours window for expiry math.

## Decisions made in the interview

- Runs in the master session via a session cron tick; not headless processes, not cloud routines.
- Auto-handle bound: read-only verification, drafts, board and tracker drafts, plus merges pre-approved per PR in chat.
- Version one kinds: Slack, email, PR and deploy, Dagster. The requests-channel watcher is folded in as a standing kind.
- Registry is a local JSON file mirrored to the board scratchpad.
- Detect and judge agents may create drafts, with pre-allowed read and draft tools.
- Per-kind expiry defaults with quiet hours.
- Script-backed checks run with no model; haiku detects, sonnet judges.
- Command name `/watch`.

## Left to the builder

- `bin/watch`: Python 3 standard library only, subcommands `add` (JSON on stdin), `list`, `stop`, `pause`, `resume`, `tick`, `update`, `status`. Atomic writes. Deploy rules and the Dagster calls live in it; the GraphQL queries can be lifted from the parity run script's `ops.py` (run and backfill state).
- Exact prompts for `detect-slack`, `detect-email` and `judge` in `dispatch-prompts.md`, following the board's placeholder convention.
- The `## Watches` scratchpad table columns in the board's `page-template.md`, and the one-line edits to the board skill (rollover arm, wrap, Drafts-today hook) and `commands/pr.md`.
- The install notes: allow-rule strings, the config block, retiring `~/.claude/commands/watch-slack.md`.
- The stale and error thresholds can be constants in the script.

## Builder-check answers (my calls, 2026-10-28)

1. **One ticking session.** Only the board's master session arms and ticks. The registry header records `owner` (session name) and `last_tick`. `bin/watch tick` refuses when another owner ticked within the last two intervals unless `--take` is passed; `/watch arm` passes `--take` only at rollover or when the user asks. Peer sessions may `add` and `list`, never tick.
2. **Pre-approved merge.** The row stores the user's words, the time and the PR head sha at approval. At fire time the master merges only when the head sha still matches, checks are green and the review decision is approved; it runs `gh pr merge <n> --squash` (the repo's merge queue takes it when one is on). A push after approval voids it: the watch raises "head moved since your approval, merge?" instead.
3. **Push notifications** use the session's built-in push tool (desktop, and the phone when Remote Control is connected). No config line. If the tool reports "not sent", the chat line and Needs-you line still stand.
4. **Reply brief** is a new row field, `reply_brief`: for chat creation it is the user's words; for the board hook it is the sent message's text plus the Drafts-today gist; for `/pr` it is empty (no reply watches). The judge receives `expect`, `reply_brief` and the thread.
5. **Follow-up watches** (`then`) hold a partial target with placeholders (`{merge_sha}`, `{run_id}`) that `bin/watch` fills from the fired watch's result at fire time. Unfilled placeholders fail the add and raise.
6. **Starting cursor.** The board hook records the sent message's ts (the drafts-check gatherer already reports it) and the cursor starts there. Chat creation starts at now unless the user names a point. Messages from the user's own Slack id or mailbox never fire a watch.
