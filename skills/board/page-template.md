# Board page template

## Database schema

One database, one row per day. Add missing properties with `notion-update-data-source` (add only; never remove `Name`, never trash the data source).

| Property | Type | Purpose |
|---|---|---|
| Name | title | `YYYY-MM-DD (Day)`, e.g. `2026-10-12 (Mon)` |
| Date | date | The day. "Today" is local `date +%F` |
| Status | select: Open / Closed | Open = the live row; Closed at rollover |
| Focus | text | The day's goal in one line (same outcomes as the Today's goal section) |
| Last sync | date with time | When the skill last wrote the page, always UTC with a `Z` suffix |
| Last edited | last_edited_time | Compared with Last sync to detect manual edits before any rewrite |

Counts (needs-you, blocked, carried, done) are not properties. They go in the chat pacing line and the Pacing section.

Default view: sorted by Date descending.

## Day row body ("Your view")

```
## Your TODOs
Manual steps only, in the order to do them; logins from the access check first. The user ticks these; sync keeps ticks and appends.
- [ ] `! <login or fix command>` (blocks: <work that waits on it>)
- [ ] <merge / meeting / send / click the user must do by hand>

## Standup
### Say this
3 to 5 sentences, one per project in priority order, as spoken: what moved, who the user is working with, what is next, what is parked. No ticket keys or technical detail.
### By project
- <Project name> (<priority>) - <KEY>, <KEY>
	- Done: <what shipped, merged, approved or delivered since the last standup, one sentence>
	- Live: <what is now live for customers, one sentence>   (only when something reached production)
	- Next: <what happens today or next, one spoken sentence>
	- Waiting on: <who> for <what> since <YYYY-MM-DD>   (omit when nothing is waiting)
### Oncall   (only when the previous row has `oncall:` Done-today lines)
- <ticket or alert> - oncall - <title> - <what was done and why it matters>

# Your view

## Today's goal
Set at rollover, confirmed by the user before the first sync writes it. Three outcomes by default, five at most, each something the user can finish today and checkable.
- [ ] <outcome 1>
- [ ] <outcome 2>
- [ ] <outcome 3>

Changes: none yet. One line per change: <HH:MMZ> <what came in> displaced <what moved out, and where it went>.

## Needs you (decisions, approvals, sends)
- [ ] <TICKET or topic>: <exact ask> (<holder: session or agent name>) <link> (since YYYY-MM-DD)
The `(since ...)` suffix is added at rollover to every carried line; the carry flag reads it.
Order: external people waiting > PR and merge gates > sub-agent approvals > housekeeping.
At most `max_needs_you` lines here; the rest go under Deferred.

## In flight (sub-agents and sessions)
| Work | Stage | Owner | Next step | Link |
|---|---|---|---|---|
Work mentions the project page from the Projects database when one exists.
Stages: planning / plan-review / awaiting-approval / implementing / code-review / pr-open / ci / ready-to-merge / done

## Blocked / waiting on others
| What | Waiting on | Since | Nudge due |
|---|---|---|---|
Example row: `| PR 123 review | reviewer name | 2026-01-05 | 2026-01-08 |`. Nudge due = since + 3 business days. Nudges are drafts, never sent directly.

## Pacing
- Capacity note: what is reasonable today and what is deliberately deferred.
- Items carried `carry_flag_days`+ days, with a close / defer / delegate proposal for each.

## Deferred
- Items past the WIP limit, kept here so they are not lost.

## Done today
- [x] Filled during the day, finalized at rollover.

Scratchpad: <link to the child page>
```

## Projects database (optional)

One row per long-lived workstream, created under the board page when the `Projects data source` config line exists. Property names are what the skill uses; the two tracker columns can be named for your tracker (for example "Jira epic", "Jira tickets").

| Property | Type | Purpose |
|---|---|---|
| Name | title | The workstream, not a ticket |
| Status | select: Active / Waiting / Parked / Done | Active = worked this week; Waiting = blocked on others; Parked = paused on purpose |
| Tracker epic | url | The epic or parent ticket |
| Tracker tickets | text | Child ticket keys, comma separated |
| Owner | text | Person or team |
| Next milestone | date | The next dated deliverable |
| Last update | date | Set by sync when the Progress log changes |
| Public hub | url | Team-facing page, if any |
| Daily rows | relation to the Daily Board, two-way (synced property "Projects") | Every day row that touched the project |
| Summary | text | One line: where we are |

Page body, identical for every project:

```
## Where we are
Three to five lines, current as of the last sync, rewritten each time.
## Next steps
- dated where known
## Decisions
| Date | Decision | Why |
|---|---|---|
Append only. The team-facing version goes on the public hub, if any.
## Open questions
- one per line, with who owns it
## Progress log
- YYYY-MM-DD: one dated line per sync that moved the project. Append only.
## Links
- tracker, chat channels and threads, public pages, repos and PRs, local paths
```

## Child page body ("Claude scratchpad - YYYY-MM-DD")

Fully rewritten on every sync. The user can read it but does not need to. Includes `## Access check (<HH:MMZ>)`: one line per configured check with pass / fixed / needs user / gap, written by the morning access check and carried through the day.

```
# Claude scratchpad

## Sources checked
| Source | When | Agent | Notes |
|---|---|---|---|
Tracker, GitHub, Slack, worktrees, memory, peer sessions (with "as of" when reused).

Row last edited after sync: <the row's Last edited value fetched right after this sync's writes; the next sync compares against it>

## Raw findings
Compact dumps per source: ticket keys, PR numbers, thread timestamps, branch names. Enough to reopen any item without re-running the gatherers.

## Drafts today
| Id | Channel or mailbox | Thread | Gist | Expected | Status |
|---|---|---|---|---|---|
One row per draft the session created today (Slack draft id, email draft id, or "held" for a tracker comment awaiting approval). Expected is `send` or `discard` (superseded drafts). Status starts `pending` and becomes `sent HH:MMZ`, `scheduled`, `discarded` or `not found` when `wrap` verifies it.

## Watches
| Id | Kind | Target | Expect | Status | Next check | Last ok check | Board line |
|---|---|---|---|---|---|---|---|
Rebuilt from `~/bin/watch list` on every sync and by `/watch arm` and `handle.md`. Read-only here; the registry file is the source of truth.

## Work registry
| Ticket | Repo | Worktree path | Branch | Stage | Plan file | PR | Last agent (name, session) | Updated |
|---|---|---|---|---|---|---|---|---|
Keyed by ticket. Rows persist across syncs and rollovers until stage is done. Survives session restarts; agent names do not, so `resume` reads this row.

## Peer sessions
| Session | Working on | Next step | Waiting on user | Blocked on | As of |
|---|---|---|---|---|---|

## Memory corrections to apply
- <memory file>: <what is wrong> -> <proposed fix>. Applied only after the user says yes.

## Open questions for the user (not yet asked)
- <project or ticket>: <question> | options: <a> / <b> | recommended: <x> | source: <agent or sync, HH:MMZ>   (asked in grouped batches of up to four; removed once answered and recorded as a Decision)

## Rollover log
- Rollover started: <UTC timestamp, written first by rollover; the next standup counts activity after it>
- Carried from <previous date>: N needs-you, M in flight, K blocked, J deferred.
- Closed on <previous date>: ...
```

## Standup section rules

The first block of the row, above Today's goal. Built once, at rollover, by the `standup-builder` prompt in `dispatch-prompts.md`, which holds the selection, grouping, oncall and waiting-on rules. Grouped by project (at most 4, priority order, from the Projects data source when configured, else the tracker epics), one Done and one Next line per project plus a Live line when something reached production, ticket keys on the project line only; small follow-ups are dropped unless the project has nothing else. It mirrors how the user gives the standup aloud: by project, naming who they work with, saying what is parked. Sync never rewrites it; a full rewrite of Your view copies an existing Standup back verbatim and never writes the placeholder above. `/board done` appends to Done today only.
