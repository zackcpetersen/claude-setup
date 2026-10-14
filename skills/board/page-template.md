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
# Your view

## Today's goal
Set at rollover, confirmed by the user before the first sync writes it. At most three outcomes the user can finish today, each checkable.
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

## Child page body ("Claude scratchpad - YYYY-MM-DD")

Fully rewritten on every sync. The user can read it but does not need to.

```
# Claude scratchpad

## Sources checked
| Source | When | Agent | Notes |
|---|---|---|---|
Tracker, GitHub, Slack, worktrees, memory, peer sessions (with "as of" when reused).

Row last edited after sync: <the row's Last edited value fetched right after this sync's writes; the next sync compares against it>

## Raw findings
Compact dumps per source: ticket keys, PR numbers, thread timestamps, branch names. Enough to reopen any item without re-running the gatherers.

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

## Rollover log
- Carried from <previous date>: N needs-you, M in flight, K blocked, J deferred.
- Closed on <previous date>: ...
```
