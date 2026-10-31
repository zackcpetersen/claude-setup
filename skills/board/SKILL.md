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
| `/board access` | Run the morning access check alone and list what still needs the user |
| `/board wrap` | End of day: verify today's drafts went out, clean merged worktrees and branches, stop strays, list temporary permission rules, write the handoff |
| `/board done <text>` / `/board defer <text>` | Tick or move one line on Your view. `done oncall: <text>` appends `- [x] oncall: <text>` to Done today, which the next standup puts under Oncall |

## Config

Read the `### Work board` section of `~/.claude/CLAUDE.md` first. It holds every machine-specific value: the Notion board page (one line, URL or id), Slack user id, watched channel ids (a channel tagged `(alerts)` is also scanned for unhandled alerts), tracker project and epics, GitHub org, worktree config path, `worktree` and `start-ticket` script paths, memory dir, watch-slack state file, the `Oncall` flag, the `Projects` data source (optional), and the WIP limits (`max_streams`, `max_needs_you`, `carry_flag_days`). The per-machine `Access checks` list now lives in `~/.claude/auth-checks.json` and is run by the `daily-auth` skill. Nothing in this skill names a company, person, channel, ticket or path.

If the section or the Notion page line is missing, stop with: "Add the `### Work board` section to ~/.claude/CLAUDE.md (see claude-md/CLAUDE.md.template in claude-setup) and set the board page."

The watch steps below (the hourly sweep cron and `wait-for pr`) run only when `~/.claude/CLAUDE.md` has a `### Watches` section; without it, skip them.

Notion setup happens on every run, so any empty page works: fetch the page, find its inline database and that database's `collection://` data source, and add any schema column from `page-template.md` that is missing (`notion-update-data-source`, add only). Cache the data source url in the scratchpad for the day.

Prompts live in `dispatch-prompts.md`; the page layout and database schema live in `page-template.md`.

## access (morning access check)

Runs once per day, before the first gatherer dispatch: at rollover, on the first sync of a day whose scratchpad has no `## Access check` section, or on `/board access`. It runs on its own: the user never has to ask for it or remember a login. Its job is to make sure the session holds every credential the day's work needs up front, so nothing stalls on the user later if they step away.

1. Read `~/.claude/daily-auth-last-run.json`; if it is not today's, run the `daily-auth` skill. Copy each of its `needs_user` lines to the top of the row's `## Your TODOs` section. Then run only the extra checks step 2 adds.
2. Anticipate: scan Today's goal, Needs you, the In-flight table and the Work registry for environments, hosts, repos or services they name (a prod health check needs the prod profile; an SFTP push needs that key; a database question needs that env file). Add a check for each one `~/.claude/auth-checks.json` already knows; name any it does not know as a gap. Run those extra checks and their fixes the way `daily-auth` does (fix right away, interactive fixes with a long timeout, anything the session cannot run goes to `## Your TODOs` as `! <fix>` marked "blocks: <what work waits on it>").
3. Record the results in the scratchpad as `## Access check (<HH:MMZ>)`, one line per check with pass / fixed / needs user / gap. Before dispatching any agent that needs a failed credential, re-run that one check; if it still fails, tell the user which TODO line unblocks it instead of dispatching.


## sync

1. Read config and do the Notion setup above. Find the row with `Status = Open` (query the data source; fall back to fetching it). If none, or its Date is not local `date +%F`, run rollover first. If more than one row is Open, keep the newest and close the rest.
2. Run the access check if it has not run today. Then in ONE message dispatch four Explore gatherers from `dispatch-prompts.md`: `tracker-status` (opus), `slack-status` (opus), `github-status` (sonnet), `email-status` (sonnet; skipped when config has no `Email` line). Fill `{{oncall}}` from config; when it is `no`, the slack gatherer skips alert channels and nothing alert-shaped (monitors, error-tracker issues, alert tickets) goes on the page. Read `MEMORY.md` inline. Message idle peer sessions with the handoff ask only on rollover or `--sessions`; otherwise reuse the scratchpad's last answer marked "as of <time>". Never wait on a peer reply to write the page.
3. Merge into the template. Keep `## Your TODOs` at the top of the row: only steps the user must do by hand (logins, merges, meetings, clicks, sends of approved drafts), one checkable line each in the order they should happen, with login lines first; keep the user's ticks, add new lines, never move agent-held approvals in from Needs you. Never rewrite the Today's goal section: tick outcomes that are done, and when a new item outranks a goal outcome (an external person waiting, a deadline today, an alert on owned work), propose the swap in chat and write it under Changes only after the user says yes; the displaced outcome goes to Needs you or Deferred. Every Needs-you line names the holder and the exact ask. Blocked rows get nudge-due = since + 3 business days. Items carried `carry_flag_days`+ are flagged under Pacing. Anything past `max_needs_you` goes to Deferred, ordered: external people waiting > PR and merge gates > sub-agent approvals > housekeeping.
4. Write Notion (rules below). Every draft the session creates (Slack, email, tracker comment held for approval) gets a row in the scratchpad's `## Drafts today` table the same turn: id, channel or mailbox, thread ts or message id, one-line gist, status (`pending`, then `sent`, `scheduled` or `discarded` once known); `wrap` verifies the table at the end of the day. The hourly sweep covers replies to sent drafts. The scratchpad rewrite rebuilds from the PREVIOUS scratchpad plus the new findings: Work registry rows persist until their stage is done, the Peer sessions table and the open outreach thread list carry forward. On a sync run by rollover, after the Your view write: if the row has no `## Standup` yet, dispatch `standup-builder` (sonnet, inputs as its placeholders list; fill `{{projects}}` from the Projects data source when configured: one line per row with name, Priority and the ticket keys named on its page) on this run's gatherer replies and insert its output at the top of the row (`insert_content`, position start); if one exists, leave it and say so. Set `Last sync`, then fetch the row's `Last edited` and store it in the scratchpad as `Row last edited after sync: <ts>`.
5. Print only Your view plus one pacing line that starts with goal progress (`goal 1/3`), then "Memory corrections to apply" if any. Apply memory edits only after the user says yes.

## Projects database

When config names a `Projects` data source, each long-lived workstream has one row there (schema and page body in `page-template.md`: Status, tracker epic, tracker tickets, Owner, Next milestone, Last update, Public hub, Summary, and a two-way `Daily rows` relation to the board). If the config line is present but the data source does not exist yet, create it under the board page with `notion-create-database` from that schema and tell the user the new `collection://` id to paste into config. Its page body holds `## Where we are`, `## Next steps`, `## Decisions` (append-only table), `## Open questions`, `## Progress log` (dated, append-only) and `## Links`.

- Sync: for every project that moved today (a PR merged, a decision, a reply, a blocker cleared), append one dated line to its Progress log, rewrite `Where we are`, set `Last update`, and add today's row to `Daily rows`. Targeted `update_content` edits only; never rewrite Decisions or the Progress log.
- Decisions: when the user says something was decided, append a row to that project's Decisions table the same day. The public hub (if any) gets the team-facing version; the project page gets the private one.
- Daily row: the In-flight table's Work column mentions the project page, so every day links to the long-lived notes. Rollover carries the mentions.
- Memory files keep pointers and how-to-apply rules; project narrative moves to the project page. Propose, under "Memory corrections to apply", trimming any memory file whose facts now live on a project page.
- New workstream: propose a row in chat; create it only after the user says yes.

## Open questions (grouped interviews)

Questions for the user that surface mid-work (a seeding agent unsure of an owner, a conflicting fact, a choice between two shapes, a stale credential) are never left inside a long report or dropped. They queue and get asked in batches.

- Queue: every open question goes to the scratchpad's `## Open questions for the user (not yet asked)` as one line: `- <project or ticket>: <question> | options: <a> / <b> | recommended: <x> | source: <agent or sync, HH:MMZ>`. Agent reports are scanned for them on arrival ("unsure", "left out", "conflict", "may be stale", "needs a decision").
- Ask with `AskUserQuestion`, up to four questions per call, each with the recommended option first and marked `(Recommended)`, grouped by project. Ask when any of these is true: the queue holds 3 or more; a queued question blocks work the user is waiting on (ask that one now, with whatever else is queued); the user turns to the board (a sync, a status ask, a "what's next"); or the oldest queued question is older than 60 minutes. Never ask one question at a time outside those moments, and never ask the same question twice.
- Record each answer the same turn: a Decisions row on the project page (date, decision, why), a Needs-you or TODO line if it creates work, and remove the line from the queue. An answer of "later" moves the line to Deferred with the date.
- Questions the user has already answered in chat count as answered: check the conversation and the Decisions tables before queuing.

## Keeping facts current

The board's notes (scratchpad, memory, the user's own tracker comments) are snapshots. Other people's work keeps moving between syncs.

- A draft or page line that states a fact about someone else's work (their PR merged, a blocker still open, a report still failing) must be checked against the primary source on the same day: the GitHub report's "Epic PRs by others" section, `gh pr view`, or the Slack thread. If it cannot be checked, write it as a question to that person or mark it `as of <date>`.
- The tracker report's "Stale snapshots" lines name the user's own status comments that are 3+ business days old. Treat every claim in them as unverified; show them in Pacing as "snapshot, N days old, verify before relying on it" and propose a refresh of the comment once the facts are confirmed.
- When a sync proves a note wrong, the correction goes to "Memory corrections to apply" and, for tracker comments, to Needs you as a one-line refresh for the user to approve.

## rollover

Run the access check first (section above). Create today's row (`Name` = `YYYY-MM-DD (Day)`, Date, Status Open) and its scratchpad child. If a row with today's Date already exists (the user pre-created it to park items for today), reuse it: set its Status Open, keep every line already on it, and merge the carried items in under the matching headings instead of creating a second row. Into Your view copy unchecked Needs-you, non-done In-flight, all Blocked and Deferred lines; append ` (since YYYY-MM-DD)` to each carried line that lacks one, using the previous row's Date (the carry flag compares that date to today). Into the new scratchpad copy every Work registry row whose stage is not done, the Peer sessions table, and the open outreach thread list from Raw findings. Write the Rollover log on both pages, starting with `Rollover started: <UTC time this rollover began>`, then listing each unmet goal outcome from the previous row with a one-line reason. Set the previous row Closed.

Then set the goal: propose outcomes for today, three by default and never more than five, drawn from unmet outcomes, carried Needs-you lines, nudges due today, meetings the user must attend and dated deadlines, each one something the user can finish today. Ask the user to confirm or edit before writing it (this is the one place rollover waits on the user). Write the confirmed outcomes under Today's goal and the same outcomes in one line in the Focus property. Then sync; its step 4 builds the standup. After that sync, delete and re-create the `watch` skill's hourly sweep cron (see the watch skill).

## start

1. Guard: refresh every registry row's stage with the `status` derivation below (files and `gh`, not the scratchpad's possibly day-old peer answers), then count streams whose stage is planning, implementing or code-review across this session and peers; refuse at `max_streams` and name what to finish first. Confirm the ticket exists; resolve the repo from the argument or the ticket, else ask.
2. `~/bin/worktree <repo> <TICKET>` (one command, inline).
3. Planner (opus) from `dispatch-prompts.md`. It writes `~/.claude/plans/<TICKET>.md`, self-reviews it, returns a summary. Registry stage: `awaiting-approval`.
4. Ask the user: approve, revise with notes, or park.
5. Implementer (opus): executes the plan, writes tests, runs nothing, commits nothing. Stage `implementing`.
6. Reviewer (opus, fresh): reviews the WORKING TREE (`git -C <worktree> diff HEAD` plus untracked files from `status --short`), since nothing is committed yet, with `/self-review implementation` against the plan and ticket. No `/code-review` here; `/pr` runs it on the real PR. One fix loop if must-fix findings. Stage `code-review`. Present the diff summary.
7. The user's "ship it" approves committing and pushing the listed files, nothing more. Dispatch the pr agent (opus) with that approval pre-attached. If `/pr`'s self review or CI produces fixes, the agent does not apply them: it reports the combined list and stops; the master session asks the user and dispatches a fix pass. Stage `pr-open` -> `ci` -> `ready-to-merge`. The user merges, or the master merges through a `wait-for pr` started with the user's approval (`watch` skill).
8. Update the registry row and In-flight table on every stage change. When a registry row first gets a PR, propose a `wait-for pr` per the `watch` skill and start it on a yes.

## resume and status

Derive the stage from durable facts first: plan file present, `git -C <worktree> status --short`, `git -C <worktree> log origin/<branch>..HEAD`, `gh pr view --repo <repo> --head <branch>`. Message an agent only if `ListAgents` shows it alive. `resume` dispatches the agent for the derived stage.

## wrap (end of day)

Runs when the user says the day is done ("wrap up", "end of day", "clean up") or on `/board wrap`. It leaves the machine and the board in the state rollover expects the next morning. Nothing here sends, posts or removes a permission rule on its own.

1. **Drafts.** Every draft the session created today is listed in the scratchpad's `## Drafts today` table (id, channel or mailbox, thread, gist, status). Dispatch `drafts-check` (sonnet, Explore) from `dispatch-prompts.md` with that table: for each draft it reads the target thread, channel or mailbox and reports SENT (UTC time, message ts or id, and first words), SCHEDULED, DISCARDED (superseded drafts must show nothing posted) or NOT FOUND. Update the table and put every NOT FOUND or wrongly posted draft under Needs you.
2. **Repos.** For every row in the Work registry and every worktree listed by `git worktree list` in each repo of the worktree config: if its PR is MERGED or CLOSED (`gh pr view --repo <repo> --head <branch> --json state`) and `git -C <worktree> status --short` is empty, remove the worktree, delete the local branch, and fast-forward main (`git fetch`, `git merge --ff-only origin/main`). A dirty worktree or an open PR is left alone and listed. Never discard local edits, never force anything.
3. **Processes and tasks.** `pgrep -fl` for scripts started from the session scratchpad and any background shell the session started that is still running; stop the ones whose work is finished (their log says so or their PR merged), list the rest with what they wait on.
4. **Permissions.** List every allow rule added to a settings file today (the session notes them under Your TODOs when it adds one, with the reason). Ask the user which to remove; remove only on a yes.
5. **Agents.** `ListAgents`: stop (`TaskStop` by name) every idle agent whose work is done, so the task list only shows live work; a running agent gets one status message and goes under Needs you if it is silent for more than 10 minutes. Stopped agents cannot be resumed, so anything still needed from one is read from the scratchpad or files first.
6. **Board and handoff.** Tick the goal outcomes that are done, add one `HH:MMZ: wrapped` line under Pacing with goal progress and what carries to tomorrow, refresh the scratchpad's Agents line, and write the handoff file the `## Handoffs` section of `~/.claude/CLAUDE.md` asks for (open PRs with CI and review state, blockers and on whom, unsent drafts verbatim, running waits (the background task ids and commands this session tracks), the exact next command). Then delete the hourly sweep cron (`CronList`, `CronDelete`); rollover re-creates it.

Print: drafts verified (counts and any problems), what was removed, what was left and why, the permission rules awaiting a decision, and the handoff path.

## Notion write rules

- Read `notion://docs/enhanced-markdown-spec` before the first write of a session.
- Scratchpad child page: `replace_content` every sync.
- The Standup section is written once at rollover and never rewritten. A `replace_content` of Your view copies an existing Standup back verbatim and never writes the template placeholder.
- Your view: compare the row's current `Last edited` with the `Row last edited after sync: <ts>` line in the scratchpad. Exact match means the user has not touched the page and `replace_content` is safe. Anything else means targeted `update_content` edits per line, never a full rewrite. `Last sync` is a human-facing timestamp only; the skill's own writes bump `Last edited`, which is why the stored value is the comparison point.
- Schema changes: add properties only. Never trash the data source or its `Name` property.
- Write `Last sync` as UTC with a `Z` suffix (`date -u +%Y-%m-%dT%H:%M:%SZ`).
- Every board write passes `allow_async: false`. Async `update_content` calls return a task id and can fail silently, and a later edit that assumes the earlier one landed then fails to match. Chained edits need each result before the next.

## Model discipline

Pass `model` on every dispatch. Planner, implementer, reviewer, pr agent, tracker and slack gatherers: opus. GitHub gatherer, standup-builder and other mechanical work: sonnet. The main session never runs the external gathering (tracker, GitHub, Slack) itself; reading local files like `MEMORY.md` inline is fine.

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
| Firing board edits with `allow_async: true` | They can fail silently and leave the page stale. Always `allow_async: false`, and re-fetch before a `replace_content` |
| Relaying the user's approval to a peer session | Peer sessions treat a relayed go as unapproved, even quoted verbatim. For anything a peer holds (open a PR, send a draft, commit), tell the user to type the approval in that session; the master session relays information only |
| Applying memory corrections automatically | Propose them; apply only on a yes |
| Drafting a reply that asserts the state of someone else's PRs or blockers from the board's own notes | Check the primary source first (Epic PRs by others, `gh pr view`, the thread) or ask them; notes older than a business day are snapshots |
| Building the standup from the board's Done-today ticks alone, or re-running the gatherers for it | Ticks miss untracked work (merges, approvals, replies). Feed it the gatherer replies this rollover already has |
| Tracking alerts, monitors or error-tracker issues when the user is not on call | Read the `Oncall` flag; `no` means alert channels are not read and alert items never reach the page |
| Asking the user for a login or VPN mid-day, or listing a login as a TODO instead of running it | The access check runs the `daily-auth` skill at the start of the day, which runs every fix itself (the user approves the prompt); the board adds checks for the day's environments. Only fixes that cannot run from the session go under Your TODOs |
| Removing a worktree or branch whose PR is still open, or a dirty one, during wrap | Only MERGED or CLOSED PRs with a clean tree are cleaned; everything else is listed, never touched |
| Treating a draft as sent because the user said drafts are clear | A cleared draft was sent, scheduled or discarded; wrap reads the target thread to tell which, and a superseded draft must show nothing posted |
| Removing a temporary permission rule during wrap without asking | List it with the reason it was added; the user says which go |
| Rewriting Today's goal during sync, or setting it without the user | The goal is set once at rollover with the user's confirmation; sync only ticks outcomes and logs confirmed swaps under Changes |
| Leaving a sub-agent's "unsure" or "left out" items inside its report, or asking the user one question at a time as each one appears | Queue them in the scratchpad and ask in one grouped `AskUserQuestion` at the next trigger (3+ queued, blocking, the user turns to the board, or 60 minutes) |
