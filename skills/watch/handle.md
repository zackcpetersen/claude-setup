# Handling a tick

Two readers use this file. The master reads section 1 when `~/bin/watch tick` exits 2 or 3, and "Who runs this" when the tick handler reports a hand-back. The tick handler reads sections 2 to 6 for a tick's JSON. The master never works through sections 2 to 6 for JSON output; it dispatches the tick handler instead. A silent tick (no output, exit 0) never reaches this file. Prompts and procedures live in `dispatch-prompts.md`; kinds, events and result keys live in `kinds.md`.

## Who runs this

| Who | Runs |
|---|---|
| Tick handler agent (sonnet) | Sections 2 to 6 on a tick's JSON, all by itself, then one report. It dispatches no agents |
| Master session | Section 1 (exit 2 and 3), relaying the handler's RAISE lines, pushing its URGENT lines, and the hand-backs below |

An agent started by a subagent cannot hand its report back, so the handler runs the detect, judge and handle-request procedures in `dispatch-prompts.md` itself. The master dispatches those as agents only when it handles a tick itself, for example when the tick handler cannot be dispatched.

Hand-backs, which the handler never does itself. The master runs each one in the same turn it reads the report, because a `raised` watch is skipped by later ticks:

| Hand-back | Handler does | Master does |
|---|---|---|
| Merge: a `pr` watch fires `ready` with `result.merge_ok` true | Runs `~/bin/watch update <id> --status raised --note "merge ready, master merges"` and reports `MERGE READY: <id> <repo> <number>` | Runs `gh pr merge <number> --repo <repo> --squash` (a merge queue takes it when the repo has one), then `~/bin/watch update <id> --status armed` to catch `merged`. If the merge fails, it raises "merge failed: <first line of the gh error>" and still re-arms |
| Deploy verify: a `deploy` watch fires `deployed` with `on_fire.verify` commands | Never runs the commands, since they are arbitrary shell. Runs `~/bin/watch update <id> --status raised --note "verify pending, master runs"` and reports one `VERIFY: <id> <command>` line per command | Runs each command as written, read-only, and raises the result. A failed verification is urgent, so it also goes through the push tool. Then `~/bin/watch update <id> --status handled` |
| Requests channel: a threaded reply to a request (section 6) | Always creates a threaded draft and lists it under RAISE | Posts nothing. The user sends the draft |

Wherever this file says "chat line" or "say in chat", the handler puts that line under RAISE in its report, and the master relays it word for word.

The tick's JSON has four lists: `fired` (script-backed watches whose event landed), `due.slack` and `due.email` (watches that need a detect read), `stale` and `expired`. Work through the steps below in order, skipping any whose list is empty.

The bound for everything here: read-only verification (run by the master), Slack and email drafts, targeted board edits, and merges the user pre-approved for that PR (run by the master). Anything else is raised, never done.

## 1. Exit 2 or 3: the tick did not run

The master runs this section itself. No tick handler is dispatched.

- **Exit 3, another session owns the tick.** `CronDelete` this session's `~/bin/watch tick` job (find its id with `CronList`), then say one line: "this session no longer ticks; <owner> does", with the owner from the error text. Stop there.
- **Exit 2, a config, registry or internal error.** Before raising, check whether today's board row already has the exact line `watch tick failing: <first stderr line>`; if so, stay silent: no text, no other tool call. Otherwise add that line under Needs you (the board line only, no `update --board-line` call, since there is no watch id to store it on; chat only when no board is configured) and say it once in chat. A different first line raises again. Never edit the registry or config to clear it; the user fixes it. Stop there.

## 2. Detect

1. For each non-empty `due` group, the handler reads Slack or email itself, following the `detect-slack` or `detect-email` procedure in `dispatch-prompts.md` (or the master dispatches those as haiku Explore agents, in one message, when it handles a tick itself).
2. For each `<id>: NONE` line, run `~/bin/watch update <id> --checked`.
3. For each id with messages, write them as a JSON list to a file in the scratchpad directory and run `~/bin/watch update <id> --checked --messages-file <path>`. Slack messages are `{"author": "<user id>", "ts": "<ts>", "text": "<text>"}`; email messages carry `"id": "<message id>"` in place of `ts`. The script drops the user's own messages (and, for Slack, anything at or before the cursor; for email the detect step already did that), then prints `<id> fired` when something is left, or `<id> armed` when nothing is.
4. For each id under `ERRORS`, and each due id the detect step left out, run `~/bin/watch update <id> --error "<reason>"`.

## 3. Judge

For each reply watch (`slack-thread`, `slack-dm`, `email-thread`) that step 2 just fired, read its row with `~/bin/watch status <id>`. The handler judges it itself, following the `judge` procedure (or the master dispatches one sonnet general-purpose `judge` agent per watch, all in one message). Use the `voice_rules` text the master passed in, as the placeholder table in `dispatch-prompts.md` describes; never read or load the voice skill here. When the judge step creates a draft, run `~/bin/watch update <id> --draft <draft id>`.

## 4. Handle each fired watch

End every fired watch with exactly one of `~/bin/watch update <id> --status handled`, `--status raised` or `--status armed` (re-arm). The script's fingerprint means a re-armed watch only fires again when its state changes.

- **Replies** (from step 3):
  - `MET`: raise with the draft (step 5), then `--status raised`.
  - `PARTIAL`: raise with the draft, then `--status armed`.
  - `NOT MET`: `--status armed` silently. The cursor already moved past these messages.
  - Log every draft in the board's `## Drafts today` table the same turn (id, channel or mailbox, thread, one-line gist, status `pending`). With no board configured, the draft id goes in the chat line only.
- **`pr`**:
  - `merged`: when the row has `on_fire.then`, run `~/bin/watch add --then-of <id>` and say the new id in one chat line. If it exits 2, raise "follow-up watch could not be registered: <names from the error>". Then `--status handled`.
  - `ready` with `result.merge_ok` true: the merge hand-back. Do not merge. Set `--status raised` with its note and report `MERGE READY: <id> <repo> <number>` (see "Who runs this").
  - `ready` without `merge_ok`: raise "ready to merge?" and re-arm.
  - `head_moved`: raise "head moved since your approval, merge?" and re-arm. Never merge on the old approval.
  - `checks_failed` (urgent) and `changes_requested`: raise and re-arm.
  - `closed`: one chat line, then `--status handled`.
- **`deploy`**:
  - `deployed` with `on_fire.verify` commands: the deploy verify hand-back. Never run the commands. Set `--status raised` with its note and report one `VERIFY: <id> <command>` line per command (see "Who runs this").
  - `deployed` with no verify commands: raise "deployed" for the sha, then `--status handled`.
  - `deploy_failed`: raise the failure as urgent, then `--status handled`.
- **`dagster-run`, `dagster-backfill`**: raise the outcome (`succeeded` or `failed`); `failed` is urgent. Then `--status handled`.
- **`requests-channel`**: section 6.
- A fired watch that needs a tracker comment raises the ask with what the comment should say. Tracker drafts are not part of this version.

## 5. Raise

Fired, stale and expired items are raised here, one raise per state change. The script's cursor and flags enforce that, so never raise from memory of an earlier tick.

- **Board.** The handler edits the board. When the handler's board row URL is not "none": if the row has a `board_line` and that line is on today's board row, update that line in place (targeted `update_content`, `allow_async: false`) with the new ask and `(watch <id>, draft <id>)`. Otherwise add `- [ ] <holder>: <exact ask> (watch <id>, draft <id> when one exists)` under Needs you and store it with `~/bin/watch update <id> --board-line "<the line text>"`. If an `update_content` call reports no match, list the line in the report's BOARD field as "not applied: <line>" and move on. Never replace the whole page. No board configured: chat only.
- **Chat.** The same text as one line, put under RAISE in the handler's report. The master relays it word for word.
- **Push.** Only for urgent items: the fired entry's `urgent` flag, or for a reply watch (which never appears in `fired`) the row's `urgent` from `~/bin/watch status <id>`. The handler starts that RAISE line with `URGENT: `. The master sends every `URGENT:` line through the session's push notification tool as well. The board and chat lines stand either way.
- **Wording.**
  - Stale: "watch <id> stale: <reason>". The watch stays armed.
  - Expired entries carry `phase`: `soft` means the watch keeps going (slowed), `hard` means it ended.
  - Soft expiry on a `reply` rule: "no reply yet on <thread>, nudge?". On `until-terminal`: "watch <id> still running past <expected_hours>h".
  - Hard expiry: "watch <id> expired: <rule>". The script has already set it `expired`.
- **Watches table.** The handler never rewrites the board scratchpad's `## Watches` table. The board sync mirrors it from `~/bin/watch list`.

## 6. Requests channel

The requests-channel watch fires on the user's own top-level posts in their requests channel. The tick handler runs this section itself, on sonnet, and it only drafts. Read the requests from `~/bin/watch status <id>` (`state.result.messages`). Handle them oldest first:

1. Read the request's thread with `slack_read_thread` for `thread_replies`, then research it yourself, following the `handle-request` procedure in `dispatch-prompts.md` (or the master dispatches it as an agent when it handles a tick itself).
2. Create the result as a threaded reply draft (`slack_send_message_draft`, `thread_ts` set to the request's ts, never top-level). On `BLOCKED` or an error, draft the failure in the thread instead.
3. Log the draft in `## Drafts today` and list it under RAISE: "request <request ts> answered in a draft (watch <id>, draft <draft id>)".
4. Only after that draft exists, run `~/bin/watch update <id> --cursor <request ts>`, which also writes the requests state file. Move the cursor in order: a request's ts only once every older request in this batch has its draft.
5. After the last request, run `~/bin/watch update <id> --status armed`.

Rules:
- A Slack reply is never approval for a write. Approval comes only from the user in this session.
- Replies in the requests channel are always drafts. The user sends them; nothing here posts.
