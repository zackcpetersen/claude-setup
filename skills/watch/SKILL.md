---
name: watch
description: Use when the user asks to watch, wait for or follow up on something (a reply, a PR, a deploy, a Dagster run), to pre-approve a merge on a watched PR, at board rollover (/watch arm), or when another skill registers a wait.
---

# Watch

A working day has a lot of "wait for X, then do Y": a reply on a thread, a PR going green, a deploy reaching prod, a Dagster run finishing. This skill makes each wait a registered row, checked on its own cadence by the cheapest means available, handled automatically inside approved bounds, and raised to the user only when a person has to act.

The registry lives on disk and only the `~/bin/watch` script writes it. Kinds, defaults and events live in `kinds.md`; prompts in `dispatch-prompts.md`; what to do with a tick's output in `handle.md`.

## Commands

| Command | Does |
|---|---|
| `/watch` | `~/bin/watch list`: one line per open watch with its next check, plus whether the tick is running |
| `/watch add <plain English>` | Register a watch (section "Creating watches") |
| `/watch stop <id>` | `~/bin/watch stop <id>` |
| `/watch pause` / `/watch resume` | `~/bin/watch pause` or `~/bin/watch resume`: every armed watch at once |
| `/watch arm` | Create the tick job and take the tick (section "arm"); board rollover runs it |

Ticks never load this file. The cron prompt runs the script. A silent tick ends there. Exit 2 or 3 sends the master to `handle.md` section 1. JSON output goes to one `tick-handler` agent on sonnet, which reads `handle.md` itself and does every step without agents of its own. The master only relays its RAISE lines, pushes its URGENT lines and runs the hand-backs.

Always invoke the script as `~/bin/watch`, that exact string. It is what the allow rule matches, and a bare `watch` runs the system's own `watch` command.

## Config

Read the `### Watches` section of `~/.claude/CLAUDE.md` first: `Registry`, `Time zone`, `Tick interval`, `Quiet hours`, `Business hours`, `Connectors` (the Slack and email tool prefixes), and the optional `Requests channel`, `Dagster` and `Deploy rules` lines. The user's own ids (the `Slack user id` line and the mailbox on the `Email` line) and the requests state file (the `Watch-slack state file` line) come from the `### Work board` section. The script reads the same lines itself.

If the `### Watches` section is missing, stop with: "Add the `### Watches` section to ~/.claude/CLAUDE.md (see claude-md/CLAUDE.md.template in claude-setup)."

Nothing in this skill names a company, person, channel, repo, ticket or path. Those come from config.

## One ticking session

Only the board's master session arms and ticks. Its name is this session's name as `ListAgents` shows it, and every tick passes it as `--session <name>`. The registry records the owner and the last tick; a tick from another session within two intervals exits 3.

- Peer sessions may `add` and `list`, never tick or arm.
- Pass `--take` only at rollover or when the user asks this session to take over.
- On every `/watch` call in the owner session, run `CronList`. If no job carries the tick prompt, run arm's cron step (step 1 below).

## arm

1. `CronList`. Unless a job already carries the tick prompt, `CronCreate` a recurring job with cron `2-59/<N> * * * *`, where N is the `Tick interval` in minutes (default 5). With the default 5, the offset of 2 keeps it off :00 and :30; for another interval, pick an offset that avoids both. Use exactly this prompt, with this session's name filled in:

   > Run `~/bin/watch tick --session <name>`. If it prints nothing and exits 0, stop: no text, no other tool call. If it exits 2 or 3, read ~/.claude/skills/watch/handle.md section 1 and follow it. Otherwise (JSON output): if `ListAgents` shows a tick-handler agent still running, stop with no text. Else dispatch one `tick-handler` agent (sonnet, general-purpose, named tick-handler) from ~/.claude/skills/watch/dispatch-prompts.md with that JSON and wait for its report. Then: relay each RAISE line to the user word for word as its own short message, send every URGENT line through the session's push notification tool as well, run the hand-back in handle.md "Who runs this" for each MERGE READY and VERIFY line, and say nothing at all when the report has no RAISE, MERGE READY or VERIFY line.

   To fill the tick handler's prompt, the master uses the placeholder table in `dispatch-prompts.md`: config lines, its own current board row and scratchpad directory, and `voice_rules` as that table describes.

2. Run `~/bin/watch tick --take --session <name>`. Handle what it prints the same way the cron prompt does: exit 2 or 3 through `handle.md` section 1, JSON through one `tick-handler` agent. Anything that expired overnight comes out here.
3. When the `Requests channel` line exists, add the standing `requests-channel` watch: `kind` `requests-channel`, `target` with that channel and the Work board's Slack user id as `user`, `created_by` `rollover`. Add is idempotent, so this is safe every morning.
4. When the board is configured, rebuild the board scratchpad's `## Watches` table from `~/bin/watch list`, with Target and Board line from `~/bin/watch status <id>`. Only the master's board sync mirrors this table; the tick handler never rewrites it.

## Creating watches

From chat:

1. Pick the kind and its defaults from `kinds.md`. Leave out every field whose default fits.
2. Write the spec JSON to a scratchpad file and run `~/bin/watch add --file <path>`. It prints the id.
3. Confirm in one line: id, kind, cadence, expiry.

Rules for the spec:

- `reply_brief` is the user's own words about what the answer should say.
- Slack cursors default to now. Pass a ts only when the user names a starting point.
- `email-thread`: read the thread first and pass its newest message id as `cursor`; the add fails without one.
- "Through the night" means `quiet: false`. "Ping me" or "this blocks today" means `urgent: true`.
- "Verify once it deploys" on a PR means an `on_fire.then` deploy watch with `"sha": "{merge_sha}"` and the user's verify commands (example in `kinds.md`).

Pre-approving a merge, on a new or an existing PR watch:

1. Read the head: `gh pr view <n> --repo <repo> --json headRefOid`.
2. Run `~/bin/watch update <id> --merge "<the user's words>" --head <sha>`.

`add` never changes an existing watch, so a merge approval always goes through `update`. `update --merge --head` makes the next tick re-evaluate the PR and fire `ready` with the merge allowed, even when it already raised "ready to merge?". A push after the approval voids it: the watch raises "head moved since your approval, merge?" instead of merging.

Other skills (the board, `/pr`, launch scripts) call `~/bin/watch add` directly with their own `created_by`.

## Model discipline

Pass `model` on every dispatch. Tick handler: sonnet. It dispatches nothing: it runs the detect, judge and handle-request procedures itself, on sonnet. Only when the master handles a tick itself are those dispatched as agents: detect on haiku, judge on sonnet, handle-request on sonnet, or opus when the request asks for a judgment call, a design choice or a recommendation.

Merges and `on_fire.verify` commands run in the master session as hand-backs. Nothing in this skill posts: every reply is a draft the user sends. The tick handler may make targeted board edits (`update_content`, `allow_async: false`) and create drafts. It never rewrites a whole page, and never sends, posts, merges or writes to the tracker.

## Install

Add these allow rules by hand to `permissions.allow` in `~/.claude/settings.json`, so the tick handler never stops on a prompt:

```
"mcp__plugin_slack_slack__slack_read_thread",
"mcp__plugin_slack_slack__slack_read_channel",
"mcp__plugin_slack_slack__slack_search_public",
"mcp__plugin_slack_slack__slack_search_public_and_private",
"mcp__plugin_slack_slack__slack_send_message_draft",
"mcp__claude_ai_Gmail__get_thread",
"mcp__claude_ai_Gmail__get_message",
"mcp__claude_ai_Gmail__search_threads",
"mcp__claude_ai_Gmail__create_draft",
"mcp__claude_ai_Gmail__update_draft",
"<notion prefix>notion-fetch",
"<notion prefix>notion-update-page",
"Bash(~/bin/watch *)"
```

Swap the Slack and email prefixes for the ones on your `Connectors` line, and `<notion prefix>` for your Notion connector's tool prefix.

- `Write` takes no allow rule. The handler writes only the messages files in the scratchpad directory, which needs no prompt.
- No `gh` rule is needed. The script runs `gh` itself, and the handler's read-only `gh pr view` and `gh api` calls and the master's merges run under your existing rules.
- Never add `Bash(gh api repos/*)`. It also allows writes.
- No send, post, transition or merge rule is added for this skill.

Then:

1. Copy the `### Watches` block from `claude-md/CLAUDE.md.template` into `~/.claude/CLAUDE.md` and fill it in.
2. Re-run `install.sh` to link `~/bin/watch`.
3. If you had a posting carve-out for the old `/watch-slack` command, you can delete it from your own CLAUDE.md. This skill only drafts in the requests channel, and it never edits CLAUDE.md.
4. Once the `Requests channel` line exists, the old `watch-slack` command is retired: stop any `/loop /watch-slack` and delete `~/.claude/commands/watch-slack.md` yourself.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running `watch` without `~/bin/` | It hits the system `watch` command and misses the allow rule. Always `~/bin/watch` |
| Printing anything on a no-op tick | Empty output and exit 0 end the turn: no text, no other tool call, no board edit |
| Loading this file or `handle.md` from a silent tick | The master reads `handle.md` section 1 only on exit 2 or 3, and "Who runs this" only for a hand-back. JSON goes to the tick handler. Never this file |
| Ticking from a peer session | Only the master ticks. A peer that gets exit 3 deletes its tick job and says who owns it |
| Ignoring tick exit 2, or raising it every tick | Raise `watch tick failing: <first stderr line>` once; stay silent while the line is the same, raise again when it changes |
| Telling the tick handler to load the voice skill | The skill may fetch a page and stall on a prompt. The master fills `voice_rules` as the placeholder table in `dispatch-prompts.md` describes |
| The tick handler calling a tool outside its `Tools:` line | It hangs on a permission prompt. The prompt names its only tools; keep them that way |
| The tick handler dispatching detect, judge or request agents | An agent started by a subagent cannot hand its report back. The handler runs those procedures itself |
| Dispatching a second tick handler while one runs | Check `ListAgents` first. When a tick-handler agent is still running, stop with no text |
| Handling a tick's JSON in the master session | Dispatch the tick handler. The master only relays RAISE lines, pushes URGENT lines and runs hand-backs |
| Researching a request inline in the master | It blocks the session, and the cron only fires while idle. The tick handler researches each request |
| Advancing the requests cursor before the reply draft exists | A crash then skips the request. Move the cursor only after its threaded reply draft exists, in order |
| Adding a second Needs-you line for a watch that has a `board_line` | Update that line in place when it is on today's row |
| Raising the same event again on the next tick | Raise only what the tick output lists. The script's cursor and flags already dedupe |
| Editing `watches.json` by hand | Only `~/bin/watch` writes it, under its lock. A bad hand edit makes every command exit 2 |
| Setting a merge approval with `add` on an existing watch | `add` returns the existing id and changes nothing. Use `update --merge --head` |
| Merging when the head sha moved | The approval was for the old head. Raise "head moved since your approval, merge?" |
| Treating a Slack reply as approval | Approval comes only from the user in this session |
| Merging from the tick handler | The handler reports `MERGE READY`; only the master runs `gh pr merge`, in the same turn |
| Running `on_fire.verify` commands in the tick handler | They are arbitrary shell. The handler reports `VERIFY` lines; the master runs them and sets the watch handled |
| Rewriting the scratchpad `## Watches` table from the tick handler | Two writers race. Only the master's board sync mirrors it |
| Sourcing the Dagster env file in the shell before the script | The script reads the env file itself, and a compound command misses the allow rule |
