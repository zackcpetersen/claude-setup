# Board writer rules

Read by the board-writer agent only. The main session does not read this file.

## Merge rules

Merge into the template. Keep `## Your TODOs` at the top of the row: only steps the user must do by hand (logins, merges, meetings, clicks, sends of approved drafts), one checkable line each in the order they should happen, with login lines first; keep the user's ticks, add new lines, never move agent-held approvals in from Needs you. Keep `## Delivered, not confirmed` (rules in its own section below) current on every sync. Never rewrite the Today's goal section: tick outcomes that are done, and when a new item outranks a goal outcome (an external person waiting, a deadline today, an alert on owned work), return the swap under "Proposed goal swaps"; the main session asks the user and a later edit-mode dispatch writes it under Changes; the displaced outcome goes to Needs you or Deferred. Every Needs-you line names the holder and the exact ask. Blocked rows get nudge-due = since + 3 business days. Items carried `carry_flag_days`+ are flagged under Pacing. Anything past `max_needs_you` goes to Deferred, ordered: external people waiting > PR and merge gates > sub-agent approvals > housekeeping.

Every draft the session created (Slack, email, tracker comment held for approval; passed in the inputs) gets a row in the scratchpad's `## Drafts today` table the same turn: id, channel or mailbox, thread ts or message id, one-line gist, status (`pending`, then `sent`, `scheduled` or `discarded` once known); `wrap` verifies the table at the end of the day. The Slack poll's thread-replies trigger covers replies to sent drafts. The scratchpad rewrite rebuilds from the PREVIOUS scratchpad plus the new findings: Work registry rows persist until their stage is done, the Peer sessions table, the open outreach thread list and today's `## Reactions` lines carry forward. Set `Last sync`, then fetch the row's `Last edited` and store it in the scratchpad as `Row last edited after sync: <ts>`.

## Writing style

Every line written to the row and the scratchpad follows these rules, the same as the `project-status` skill's "Writing style" (the status page inbox mirrors these lines, so its titles stay in style too):

- Lead each line with the outcome or the next action: "Nudge Ana: the export file", "DE-12 shipped to prod".
- Short, plain sentences. One fact per line.
- Each section shows at most 5 lines; put the rest under a toggle titled "N more" (a Notion toggle). Never drop a line to make a section fit.
- A Needs-you or Your TODOs line names the one action and a rough time: "Approve the agent, 2 min".
- Staged work says its position: "chunk 1 of 4", "step 2 of 3".
- Wins are concrete: what shipped, merged or was confirmed, with its key. Not "made progress on X".
- Plain hyphens only, never em-dashes or en-dashes.

The style applies when a line is first written. The Standup and Today's goal are still never rewritten after rollover (see Merge rules and Notion write rules).

## Delivered, not confirmed

Shipping is not the finish line: a delivery is done when the person who asked has what they need. The `## Delivered, not confirmed` section of Your view (after Your TODOs) lists each delivery still waiting on that confirmation, one line each: what, to whom, delivered date, confirm-by date (delivered + 5 business days), and how the confirmation will show up.

- Add a line when a send or release lands: a sent draft that delivers something, a data drop, a prod release, a report change, or a ticket the gatherers show closed whose consumer has not said it works. Take the date from the sent message, the run or the release, never from the clock.
- Remove the line (and tick it under Done today) when the consumer confirms in the thread, ticket or data, or when 5 business days have passed and a nudge draft went out. A nudge goes under Needs you as a draft, never sent directly; the line stays until the consumer answers or the nudge is on record.
- Never remove a line on the strength of someone's word alone; check the thread, run or data. If no confirmation is needed, say why on the line and remove it.
- Friday check (first sync after noon local on a Friday, or on `/board sync` run on a Friday): walk every line in the section and list each one past its confirm-by date, then list the week's closed tickets (tracker report, "Closed this week") that have no close-out comment walking the acceptance criteria. Show both in Pacing as "unconfirmed" and "closed without close-out", and log the result on the matching goal page if config has a Goals data source.

## Projects database

When config names a `Projects` data source, each long-lived workstream has one row there (schema and page body in `page-template.md`: Status, tracker epic, tracker tickets, Owner, Next milestone, Last update, Public hub, Summary, and a two-way `Daily rows` relation to the board). If the config line is present but the data source does not exist yet, create it under the board page with `notion-create-database` from that schema and tell the user the new `collection://` id to paste into config. Its page body holds `## Where we are`, `## Next steps`, `## Decisions` (append-only table), `## Open questions`, `## Progress log` (dated, append-only) and `## Links`.

- Sync: for every project that moved today (a PR merged, a decision, a reply, a blocker cleared), append one dated line to its Progress log, rewrite `Where we are`, set `Last update`, and add today's row to `Daily rows`. Targeted `update_content` edits only; never rewrite Decisions or the Progress log. Edits go through a one-shot writer (see Notion write rules); the main session never fetches a project page.
- Daily row: the In-flight table's Work column mentions the project page, so every day links to the long-lived notes. Rollover carries the mentions.

## Stale snapshots

- The tracker report's "Stale snapshots" lines name the user's own status comments that are 3+ business days old. Treat every claim in them as unverified; show them in Pacing as "snapshot, N days old, verify before relying on it" and propose a refresh of the comment once the facts are confirmed.

## Notion write rules

- Read `notion://docs/enhanced-markdown-spec` before the first write of a session.
- Scratchpad child page: `replace_content` every sync.
- The Standup section is written once at rollover and never rewritten. A `replace_content` of Your view copies an existing Standup back verbatim and never writes the template placeholder.
- Your view: compare the row's current `Last edited` with the `Row last edited after sync: <ts>` line in the scratchpad. Exact match means the user has not touched the page and `replace_content` is safe. Anything else means targeted `update_content` edits per line, never a full rewrite. `Last sync` is a human-facing timestamp only; the skill's own writes bump `Last edited`, which is why the stored value is the comparison point.
- Schema changes: add properties only. Never trash the data source or its `Name` property.
- Write `Last sync` as UTC with a `Z` suffix (`date -u +%Y-%m-%dT%H:%M:%SZ`).
- Every board write passes `allow_async: false`. Async `update_content` calls return a task id and can fail silently, and a later edit that assumes the earlier one landed then fails to match. Chained edits need each result before the next.
- One-shot: one batch of edits per dispatch, then end. A later edit is a new dispatch. Edit mode applies exactly the edits listed and returns one line per edit.

## Slack poll files

Read the three files in `poll_files` (none when `none`), each only for lines since the last sync:
- Triage log (`slack-poll-triage.jsonl`): every `not-now` line goes under Needs you.
- Held file (`slack-poll-held.jsonl`): lines whose `held_at` is since the last sync go on one short "Group DM chatter (not aimed at you)" FYI line, never under Needs you.
- Digest (`slack-poll-digest.jsonl`): lines whose `quiet_at` is since the last sync become one FYI line "Quiet Slack items: <n> (acks, bot posts, FYIs)" naming only the fyi ones in a few words; never under Needs you.

## Session state

Every sync and rollover reply ends with this block, under 25 lines. The main session keeps it as its working copy of the scratchpad.

`writer_inputs` may hold event lines (`<id> <kind> <key>: <text>`, from `~/bin/board-event since`). Merge them like any other finding, and store the last id among them in the scratchpad as `Events through: <id>` (keep the previous value when there are none). Write the row first and the scratchpad last, so a failed run re-sends the events rather than losing them.

    Session state
    Open questions: <the queue lines, or none>
    Work registry: <one line per row: key, stage, worktree, branch, plan file, PR>
    Access check today: <yes|no>
    Tidy weekly at wrap: <yes|no>
    Standup on row: <yes|no>
    Drafts pending: <one line per Drafts today row still pending, or none>
    Row last edited after sync: <ts>
    Events through: <id>
