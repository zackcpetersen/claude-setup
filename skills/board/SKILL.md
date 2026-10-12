---
name: board
description: Use when the user asks where things stand, what is waiting on them, what is blocked, to start, plan or implement a ticket from the master session, to roll the daily board to a new day, or at the start of a master-session day.
---

# Board

One place to see all active work. State lives in a Notion database with one row per day. Each day row holds the human-readable "Your view"; a child page "Claude scratchpad" holds machine notes and the work registry. External gathering (tracker, GitHub, Slack) and ticket work run in sub-agents; the main session coordinates, reads local files like `MEMORY.md` inline, and reports.

## Sub-commands

| Command | Does |
|---|---|
| `/board` or `/board sync [--sessions]` | Rebuild today's row from every source and print Your view |
| `/board rollover` | Close yesterday's row, create today's, carry open items forward |
| `/board start <TICKET> [repo]` | Worktree, planner, approval, implementer, reviewer, `/pr` |
| `/board resume <TICKET>` | Restart a stream from its registry row after a session restart |
| `/board status [<TICKET>]` | Stage of one or all streams, from files first, agents second |
| `/board done <text>` / `/board defer <text>` | Tick or move one line on Your view |

## Config

Read the `### Work board` section of `~/.claude/CLAUDE.md` first. It holds every machine-specific value: the Notion board page (one line, URL or id), Slack user id, watched channel ids (a channel tagged `(alerts)` is also scanned for unhandled alerts), tracker project and epics, GitHub org, worktree config path, `worktree` and `start-ticket` script paths, memory dir, watch-slack state file, and the WIP limits (`max_streams`, `max_needs_you`, `carry_flag_days`). Nothing in this skill names a company, person, channel, ticket or path.

If the section or the Notion page line is missing, stop with: "Add the `### Work board` section to ~/.claude/CLAUDE.md (see claude-md/CLAUDE.md.template in claude-setup) and set the board page."

Notion setup happens on every run, so any empty page works: fetch the page, find its inline database and that database's `collection://` data source, and add any schema column from `page-template.md` that is missing (`notion-update-data-source`, add only). Cache the data source url in the scratchpad for the day.

Prompts live in `dispatch-prompts.md`; the page layout and database schema live in `page-template.md`.

## sync

1. Read config and do the Notion setup above. Find the row with `Status = Open` (query the data source; fall back to fetching it). If none, or its Date is not local `date +%F`, run rollover first. If more than one row is Open, keep the newest and close the rest.
2. In ONE message dispatch three Explore gatherers from `dispatch-prompts.md`: `jira-status` (opus), `slack-status` (opus), `github-status` (sonnet). Read `MEMORY.md` and the watch-slack state file inline. Message idle peer sessions with the handoff ask only on rollover or `--sessions`; otherwise reuse the scratchpad's last answer marked "as of <time>". Never wait on a peer reply to write the page.
3. Merge into the template. Every Needs-you line names the holder and the exact ask. Blocked rows get nudge-due = since + 3 business days. Items carried `carry_flag_days`+ are flagged under Pacing. Anything past `max_needs_you` goes to Deferred, ordered: external people waiting > PR and merge gates > sub-agent approvals > housekeeping.
4. Write Notion (rules below). The scratchpad rewrite rebuilds from the PREVIOUS scratchpad plus the new findings: Work registry rows persist until their stage is done, the Peer sessions table and the open outreach thread list carry forward. Set `Last sync`, then fetch the row's `Last edited` and store it in the scratchpad as `Row last edited after sync: <ts>`.
5. Print only Your view plus one pacing line, then "Memory corrections to apply" if any. Apply memory edits only after the user says yes.

## rollover

Create today's row (`Name` = `YYYY-MM-DD (Day)`, Date, Status Open) and its scratchpad child. If a row with today's Date already exists (the user pre-created it to park items for today), reuse it: set its Status Open, keep every line already on it, and merge the carried items in under the matching headings instead of creating a second row. Into Your view copy unchecked Needs-you, non-done In-flight, all Blocked and Deferred lines; append ` (since YYYY-MM-DD)` to each carried line that lacks one, using the previous row's Date (the carry flag compares that date to today). Into the new scratchpad copy every Work registry row whose stage is not done, the Peer sessions table, and the open outreach thread list from Raw findings. Write the Rollover log on both pages. Set the previous row Closed. Then sync.

## start

1. Guard: refresh every registry row's stage with the `status` derivation below (files and `gh`, not the scratchpad's possibly day-old peer answers), then count streams whose stage is planning, implementing or code-review across this session and peers; refuse at `max_streams` and name what to finish first. Confirm the ticket exists; resolve the repo from the argument or the ticket, else ask.
2. `~/bin/worktree <repo> <TICKET>` (one command, inline).
3. Planner (opus) from `dispatch-prompts.md`. It writes `~/.claude/plans/<TICKET>.md`, self-reviews it, returns a summary. Registry stage: `awaiting-approval`.
4. Ask the user: approve, revise with notes, or park.
5. Implementer (opus): executes the plan, writes tests, runs nothing, commits nothing. Stage `implementing`.
6. Reviewer (opus, fresh): reviews the WORKING TREE (`git -C <worktree> diff HEAD` plus untracked files from `status --short`), since nothing is committed yet, with `/self-review implementation` against the plan and ticket. No `/code-review` here; `/pr` runs it on the real PR. One fix loop if must-fix findings. Stage `code-review`. Present the diff summary.
7. The user's "ship it" approves committing and pushing the listed files, nothing more. Dispatch the pr agent (opus) with that approval pre-attached. If `/pr`'s self review or CI produces fixes, the agent does not apply them: it reports the combined list and stops; the master session asks the user and dispatches a fix pass. Stage `pr-open` -> `ci` -> `ready-to-merge`. The user merges.
8. Update the registry row and In-flight table on every stage change.

## resume and status

Derive the stage from durable facts first: plan file present, `git -C <worktree> status --short`, `git -C <worktree> log origin/<branch>..HEAD`, `gh pr view --repo <repo> --head <branch>`. Message an agent only if `ListAgents` shows it alive. `resume` dispatches the agent for the derived stage.

## Notion write rules

- Read `notion://docs/enhanced-markdown-spec` before the first write of a session.
- Scratchpad child page: `replace_content` every sync.
- Your view: compare the row's current `Last edited` with the `Row last edited after sync: <ts>` line in the scratchpad. Exact match means the user has not touched the page and `replace_content` is safe. Anything else means targeted `update_content` edits per line, never a full rewrite. `Last sync` is a human-facing timestamp only; the skill's own writes bump `Last edited`, which is why the stored value is the comparison point.
- Schema changes: add properties only. Never trash the data source or its `Name` property.
- Write `Last sync` as UTC with a `Z` suffix (`date -u +%Y-%m-%dT%H:%M:%SZ`).

## Model discipline

Pass `model` on every dispatch. Planner, implementer, reviewer, pr agent, jira and slack gatherers: opus. GitHub gatherer and other mechanical work: sonnet. The main session never runs the external gathering (tracker, GitHub, Slack) itself; reading local files like `MEMORY.md` inline is fine.

## Common mistakes

| Mistake | Fix |
|---|---|
| Expecting a sub-agent to run inside the worktree | The Agent tool has no cwd. Put the absolute worktree path in the prompt; use `git -C <path>` or `cd <path> && ...` in every command |
| Using `isolation: "worktree"` | It skips the `worktree` script's env and dependency setup. Always use the script |
| Planner runs the plan-gate marker command | It unlocks the master session's gate, not the worktree's. The planner prompt says skip it and never call ExitPlanMode |
| Implementer runs the test suite or linter | CI verifies (CLAUDE.md CI policy). Write tests, do not run them unless the plan says the user asked |
| Treating Explore as read-only | It still has Bash and every MCP write tool. The read-only rule is a prompt rule; every gatherer prompt carries it |
| Storing agent names as the registry key | Agents die with the session. Key rows by ticket; store worktree, branch, plan file, PR |
| Two rows left Open after a crash mid-rollover | Keep the newest, close the rest |
| Rollover creates a second row for today | A pre-created row for today (parked items) is reused, never duplicated |
| Calling `/babysit-pr` from sync | It makes fixes. Sync reuses only its `gh pr list` query |
| Blocking the page write on a peer session reply | Replies can be held or expire. Write with the last known answer |
| Applying memory corrections automatically | Propose them; apply only on a yes |
