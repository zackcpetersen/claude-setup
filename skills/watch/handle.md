# Handling a tick

Read this file only when `~/bin/watch tick` printed a JSON line, exited 2 or exited 3. A silent tick (no output, exit 0) never reaches this file. Prompts live in `dispatch-prompts.md`; kinds, events and result keys live in `kinds.md`. Pass `model` on every dispatch.

The tick's JSON has four lists: `fired` (script-backed watches whose event landed), `due.slack` and `due.email` (watches that need a detect agent), `stale` and `expired`. Work through the steps below in order, skipping any whose list is empty.

The bound for everything here: read-only verification, Slack and email drafts, board edits, and merges the user pre-approved for that PR. Anything else is raised, never done.

## 1. Exit 2 or 3: the tick did not run

- **Exit 3, another session owns the tick.** `CronDelete` this session's `~/bin/watch tick` job (find its id with `CronList`), then say one line: "this session no longer ticks; <owner> does", with the owner from the error text. Stop there.
- **Exit 2, a config, registry or internal error.** Before raising, check whether today's board row already has the exact line `watch tick failing: <first stderr line>`; if so, stay silent: no text, no other tool call. Otherwise add that line under Needs you (the board line only, no `update --board-line` call, since there is no watch id to store it on; chat only when no board is configured) and say it once in chat. A different first line raises again. Never edit the registry or config to clear it; the user fixes it. Stop there.

## 2. Detect

1. For each non-empty `due` group, fill `detect-slack` (haiku, Explore) or `detect-email` (haiku, Explore). Dispatch them in ONE message.
2. For each `<id>: NONE` line, run `~/bin/watch update <id> --checked`.
3. For each id with messages, write them to a scratchpad file as a JSON list and run `~/bin/watch update <id> --checked --messages-file <path>`. Slack messages are `{"author": "<user id>", "ts": "<ts>", "text": "<text>"}`; email messages carry `"id": "<message id>"` in place of `ts`. The script drops the user's own messages (and, for Slack, anything at or before the cursor; for email the detect agent already did that), then prints `<id> fired` when something is left, or `<id> armed` when nothing is.
4. For each id under `ERRORS`, and each due id the agent left out, run `~/bin/watch update <id> --error "<reason>"`.

## 3. Judge

For each reply watch (`slack-thread`, `slack-dm`, `email-thread`) that step 2 just fired, read its row with `~/bin/watch status <id>` and fill one `judge` (sonnet, general-purpose). Fill `voice_rules` once per tick by reading the writing-voice skill's `SKILL.md` file named in `~/.claude/CLAUDE.md` and pasting its rules section (a file read only, never a page fetch); with no voice skill configured, pass "plain English, short sentences, no em-dashes". Dispatch them all in one message. When a judge returns a draft id, run `~/bin/watch update <id> --draft <draft id>`.

## 4. Handle each fired watch

End every fired watch with exactly one of `~/bin/watch update <id> --status handled`, `--status raised` or `--status armed` (re-arm). The script's fingerprint means a re-armed watch only fires again when its state changes.

- **Replies** (from step 3):
  - `MET`: raise with the draft (step 5), then `--status raised`.
  - `PARTIAL`: raise with the draft, then `--status armed`.
  - `NOT MET`: `--status armed` silently. The cursor already moved past these messages.
  - Log every draft in the board's `## Drafts today` table the same turn (id, channel or mailbox, thread, one-line gist, status `pending`). With no board configured, the draft id goes in the chat line only.
- **`pr`**:
  - `merged`: when the row has `on_fire.then`, run `~/bin/watch add --then-of <id>` and say the new id in one chat line. If it exits 2, raise "follow-up watch could not be registered: <names from the error>". Then `--status handled`.
  - `ready` with `result.merge_ok` true: run `gh pr merge <number> --repo <repo> --squash` here in the master, never in an agent (a merge queue takes it when the repo has one). Then `--status armed` to catch `merged`. If the merge command fails, raise "merge failed: <first line of the gh error>" and re-arm.
  - `ready` without `merge_ok`: raise "ready to merge?" and re-arm.
  - `head_moved`: raise "head moved since your approval, merge?" and re-arm. Never merge on the old approval.
  - `checks_failed` (urgent) and `changes_requested`: raise and re-arm.
  - `closed`: one chat line, then `--status handled`.
- **`deploy`**: on `deployed`, run each `on_fire.verify` command as written (read-only), read the output, and raise the result; a failed verification is urgent. On `deploy_failed`, raise the failure as urgent without verifying. Then `--status handled`.
- **`dagster-run`, `dagster-backfill`**: raise the outcome (`succeeded` or `failed`); `failed` is urgent. Then `--status handled`.
- **`requests-channel`**: section 6. Never research a request inline.
- A fired watch that needs a tracker comment raises the ask with what the comment should say. Tracker drafts are not part of this version.

## 5. Raise

Fired, stale and expired items are raised here, one raise per state change. The script's cursor and flags enforce that, so never raise from memory of an earlier tick.

- **Board.** When the `### Work board` section exists: if the row has a `board_line` and that line is on today's board row, update that line in place (targeted `update_content`, `allow_async: false`) with the new ask and `(watch <id>, draft <id>)`. Otherwise add `- [ ] <holder>: <exact ask> (watch <id>, draft <id> when one exists)` under Needs you and store it with `~/bin/watch update <id> --board-line "<the line text>"`. No board configured: chat only.
- **Chat.** The same text as one line.
- **Push.** Only for urgent items (the fired entry's `urgent` flag; for a reply watch, which never appears in `fired`, the row's `urgent` from `~/bin/watch status <id>`; or a failed verification), through the session's push notification tool (find it with ToolSearch). If it reports not sent, the board and chat lines stand.
- **Wording.**
  - Stale: "watch <id> stale: <reason>". The watch stays armed.
  - Expired entries carry `phase`: `soft` means the watch keeps going (slowed), `hard` means it ended.
  - Soft expiry on a `reply` rule: "no reply yet on <thread>, nudge?". On `until-terminal`: "watch <id> still running past <expected_hours>h".
  - Hard expiry: "watch <id> expired: <rule>". The script has already set it `expired`.
- **Mirror.** After any raise or handled watch, refresh the board scratchpad's `## Watches` table from `~/bin/watch list`, with Target and Board line from `~/bin/watch status <id>` (when the board is configured).

## 6. Requests channel

The requests-channel watch fires on the user's own top-level posts in their requests channel. Read the requests from `~/bin/watch status <id>` (`state.result.messages`). Handle them oldest first:

1. Post a one-line ack as a threaded reply to the request (`thread_ts` set to the request's ts, never top-level).
2. Dispatch one `handle-request` agent for it (sonnet, or opus when the request asks for a judgment call, a design choice or a recommendation). Fill `thread_replies` by reading the request's thread first. Do not wait on it in the foreground; the cron only fires while the session is idle.
3. When the agent returns, post its text as a threaded reply. On `BLOCKED` or an agent error, post the failure in the thread instead.
4. Only after that reply posts, run `~/bin/watch update <id> --cursor <request ts>`, which also writes the requests state file. Move the cursor in order: a request's ts only once every older request in this batch has its reply posted.
5. After the last request, run `~/bin/watch update <id> --status armed`.

Rules:
- A Slack reply is never approval for a write. Approval comes only from the user in this session.
- Posting needs the user's own CLAUDE.md carve-out that allows threaded replies in the requests channel during the `watch` skill. Without it, create drafts (`slack_send_message_draft`) instead of posting, and log them in `## Drafts today`.
