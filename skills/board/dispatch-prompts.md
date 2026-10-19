# Board dispatch prompts

Every `{{placeholder}}` maps to a key in the `### Work board` section of `~/.claude/CLAUDE.md`. Fill them in before dispatching. Pass `model` on every dispatch. Gatherers use `subagent_type: Explore`; planner, implementer, reviewer and pr agents use `general-purpose`. Never use `isolation: "worktree"`.

## Placeholder sources

| Placeholder | Comes from |
|---|---|
| `user_name` | `git config user.name`, or a name line in `~/.claude/CLAUDE.md` if present |
| `tracker_site`, `tracker_mcp_prefix` | the `### Issue Tracker` section of `~/.claude/CLAUDE.md` |
| `ticket_url` | that section's ticket URL format |
| `master_session_name` | this session's name from `ListAgents` |
| `since_date` | the previous row's Date, else 7 days ago |
| `today` | local `date +%F` |
| `approved_files` | the user's ship-it turn |
| `epic_child_keys` | the child keys under `tracker_epics` listed under those epics in the previous scratchpad's "Epic rollups" section, never from the project fallback (empty on the first run or when `tracker_epics` is empty; the GitHub gatherer then skips step 4) |
| `registry_rows`, `outreach_threads`, peer answers | the previous scratchpad; empty on the first run, which the prompts tolerate |
| `oncall` | the `Oncall` line of the `### Work board` section (`yes` or `no`) |
| `slack_user_id`, `slack_channels`, `tracker_project`, `tracker_epics`, `github_org`, `worktree_config`, `worktree_script` | the `### Work board` section of `~/.claude/CLAUDE.md` |
| `prev_done_today`, `prev_rollover_time` | the previous row's Done today section, and the `Rollover started:` line in its scratchpad's Rollover log (else its Date at 00:00 UTC) |
| `tracker_report`, `github_report`, `slack_report` | this rollover's gatherer replies, verbatim |
| `confirmed_goal`, `carried_needs_you`, `blocked_rows` | the new row's Today's goal, Needs you and Blocked sections after the carry |

Read-only rule, included verbatim in every gatherer prompt:

> READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes. If a step would need one, report what you would have done instead.

---

## tracker-status (model: opus, Explore)

```
You are gathering a read-only status snapshot of {{user_name}}'s issue tracker work ({{tracker_site}}, tools `{{tracker_mcp_prefix}}*`). Today is {{today}}. READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes.

Run these queries. Each is an intent, not syntax: map it to this tracker's own tools (JQL on Jira, list_issues filters on Linear, search on GitHub Issues). Filter by state type (open, in progress, done) rather than status names, which the tracker may reject. When a query has no equivalent in this tracker, skip it and say so in the report (for example, watchers on Linear are subscribers). Compact view; fields: key, summary, status, priority, type, assignee, reporter, updated, resolved date, parent, labels, due date. Report summary and parent key on every ticket, whichever query found it.
1. Open tickets assigned to {{user_name}}, highest priority and most recently updated first.
2. Open tickets reported by {{user_name}} and assigned to someone else.
3. Children of each epic or project in {{tracker_epics}}, grouped by status. When none are configured, use the projects of the tickets from query 1 instead.
4. In-progress tickets in {{tracker_project}} updated in the last 14 days, then keep only those whose status name contains "review" (case-insensitive).
5. Tickets {{user_name}} completed in the last 14 days.
6. Open tickets {{user_name}} watches that are assigned to someone else, updated in the last 7 days.
7. {{user_name}}'s unread notifications.

For each in-progress or in-review ticket from query 1, read the description's progress notes and the last 3 comments: next concrete step, blocked on whom or what, and whether anything waits on {{user_name}} (decision, comment, approval). Treat a batch of tickets all updated in the same minute with no comments as not actually updated.

Return under 120 lines:
- Table A: open tickets assigned to {{user_name}}: key, summary (the ticket title, always included), status, priority, epic, updated, next step, blocked-on, waiting-on-user (yes + what / no).
- Table B: open tickets {{user_name}} reported or watches, assigned to others: status, what is expected from them.
- Epic rollups for {{tracker_epics}} (or the fallback projects from query 3, labeled as such): children by status, stalled children (In Progress, no real update 7+ days), unassigned children.
- Dates in the next 30 days, including dates that only appear in ticket text.
- "Things that look off": In Progress with 10+ quiet days, Done here but open elsewhere, unassigned High priority updated in 14 days, epics in the wrong status.
- "Stale snapshots": every open ticket where the newest comment is by {{user_name}} and is 3+ business days old and reads as a status list, checklist or plan (it names other people's work, blockers or PRs). One line each: key, comment id, age in days, what it claims. The master session treats those claims as unverified until the GitHub report or the owner confirms them.
- "Activity since {{since_date}}": one line per ticket {{user_name}} resolved, transitioned or commented on since then: key, summary (the ticket title), parent key, labels, what happened, UTC timestamp.
- "Unread notifications": one line each for items not already covered above: key, summary, who, what, when. If the tracker has no notifications tool, one line saying it was skipped.
```

## github-status (model: sonnet, Explore)

```
You are gathering a read-only snapshot of {{user_name}}'s GitHub and local git state (org {{github_org}}). Today is {{today}}. READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes. Use `gh` and read-only `git` only.

Part 1, GitHub:
1. Open PRs by the user, the same query `/babysit-pr` uses:
   gh pr list --author @me --state open --json number,title,headRefName,url,reviewDecision,isDraft,mergeable,mergeStateStatus
   Run it per repo listed in {{worktree_config}} (`jq -r '.repos[].repo_path'`) plus any repo named in the registry. For each PR: `gh pr view <n> --repo <repo> --json statusCheckRollup,reviewRequests,reviews,comments,updatedAt,baseRefName` and summarize CI (name failing checks), review state and who was asked how long ago, conflicts, unresolved comments including bot comments, draft or not, age.
2. PRs requesting the user's review: `gh search prs --review-requested=@me --state=open --owner {{github_org}}`. Separate direct requests from team requests. Mentions: `gh search prs --mentions=@me --state=open --owner {{github_org}}`.
3. For each branch in the work registry (passed in below), `gh pr list --repo <repo> --head <branch> --state all`.
4. Epic PRs by others: for each repo, `gh pr list --repo <repo> --state all --search "<KEY> updated:>={{since_date}}" --json number,title,headRefName,author,state,mergedAt,url` for every child key the tracker report or the registry names under {{tracker_epics}} (pass the list in below). One line each: repo, PR, title, author, state, merged date. This is how the board learns that someone else's PR moved a shared workstream.
5. Dependabot PRs on the main repos that fix an open security alert: count plus the ones that are major bumps.

6. Activity since {{since_date}}: `gh search prs --author @me --merged ">={{since_date}}" --owner {{github_org}}` and `gh search prs --reviewed-by @me --updated ">={{since_date}}" --owner {{github_org}}`, plus approvals and reviews received on the user's PRs. One line each: repo, PR number, title, head branch, what happened, UTC timestamp, ticket key if the title or branch names one.

Part 2, local checkouts:
1. `{{worktree_script}} list`, then loop over `.repos[].repo_path` and `.repos[].worktree_base` from the worktree config json ({{worktree_config}}) and scan each git checkout under them (the repo itself, and every directory inside each worktree base).
2. Per checkout: branch, `git -C <path> status --short | wc -l` plus top files, unpushed commits (`git -C <path> log --oneline @{upstream}..HEAD 2>/dev/null | wc -l`), last commit date, open PR for the branch.
3. Flag: uncommitted real work (at risk), branches never pushed, stale (PR merged or closed, or no own commits), broken worktrees, files that look like secrets (`.env*` untracked).

Registry rows to check: {{registry_rows}}
Epic child keys to search for: {{epic_child_keys}}

Return under 120 lines: Table A open PRs; Table B review/reply owed; "Epic PRs by others"; "Activity since {{since_date}}"; named branch states; Table C local checkouts with a suggested disposition (active / at-risk / stale-remove); "Things that look off".
```

## slack-status (model: opus, Explore)

```
You are gathering a read-only snapshot of what is waiting on {{user_name}} (Slack user {{slack_user_id}}) in Slack. Today is {{today}}. READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes. Use only the Slack read and search tools.

Note: the `<@user>` mention search filter is unreliable (it can return all channel traffic). Read the named channels, threads and DMs directly and say which coverage you have.

Gather:
1. Each watched channel in {{slack_channels}}: read since {{since_date}}. For every top-level post or thread that names or is addressed to the user, decide whether the user replied after the ask. List unanswered ones: channel, who, when, one-line ask, thread ts.
2. DMs and group DMs since {{since_date}}: messages from others the user has not answered, with the ask.
3. Outreach threads the user owns (from the previous scratchpad, passed in below): new replies since last sync, who the ball is with, whether a nudge is due (3 business days of silence), whether a nudge already went out.
4. On-call this week: {{oncall}}. If `no`, skip this step entirely, do not read the `(alerts)` channels, and leave the "Alerts possibly unhandled" section out. If `yes`: only for channels tagged `(alerts)` in {{slack_channels}}, anything in the last 3 days tagged to the user's area that has no recovery or reply. Skip untagged channels either way.
5. `from:<@{{slack_user_id}}> after:{{since_date}}`: commitments the user made that are still open.

Outreach threads to check: {{outreach_threads}}

Return under 120 lines with thread ts values on every line: "Waiting on user" (with urgency today / this week / low), "Waiting on others" (per thread: ball with, since, nudge due or sent), "Commitments made since {{since_date}}", "Posts sent since {{since_date}}" (one line per post or reply by the user: channel, thread, gist, UTC time), "Alerts possibly unhandled", "Things that look off", and a one-line coverage caveat.
```

## standup-builder (model: sonnet, general-purpose, rollover only)

Dispatched after the goal is confirmed and the sync gatherers have returned. It reads only what it is given and calls no tools.

```
You are writing {{user_name}}'s daily standup from the inputs below. They say it out loud in a team standup in about a minute, grouped by project, so the shape follows the projects, not the ticket list. Use no tools. Return only the markdown block, nothing before or after it.

The output is exactly this shape, in Notion markdown, nested with tab characters:

## Standup
### Say this
<3 to 5 sentences, one per project in priority order, the way {{user_name}} would speak: what moved, who they are working with on it (first names of reviewers, stakeholders or teammates), what is next, and which project is parked or lower priority. Project names in plain words ("the claim export work", "the vendor handover"). No ticket keys, PR numbers, branch names or system internals. End with one thanks when someone unblocked them since the last standup; otherwise no thanks line.>
### By project
- <Project name> (<priority>) - <KEY>, <KEY>
	- Done: <what shipped, merged, approved, decided or delivered since the last standup, one sentence, plain English>
	- Live: <what is now live for customers, one sentence>
	- Next: <what happens today or next, one spoken sentence>
	- Waiting on: <first name or team> for <what> since <YYYY-MM-DD>
### Oncall
- <ticket or alert> - oncall - <title> - <what was done and why it matters>

How to fill it:
1. Candidate items: every line of PREVIOUS DONE TODAY, plus every line in the reports' "Activity since" and "Posts sent since" sections dated after {{prev_rollover_time}}, plus any other dated event in the reports that {{user_name}} did or that moved their work (merges, approvals received, transitions). Merge duplicates. Drop board and session upkeep (rolling the board, memory edits, stopping or replacing agents, branch cleanup).
2. Group every item by project. A project is a row of PROJECTS when that list is given, else a parent in {{tracker_epics}}, else the system or customer the item is about. Key each item to a ticket the same way as before: a key in its text, else the PR-to-ticket mapping in the GitHub report, else the ticket whose title names the same project. Items with no ticket stay in their project's Done line when they are meaningful (a kickoff, an incident, a customer delivery); otherwise drop them.
3. At most 4 projects, in PROJECTS priority order (P1 first), else by how much moved. Projects with nothing done and nothing planned are left out. A project the user has deprioritised (a Deferred or Pacing line says parked, back burner, lower priority, or pushed to a later week) still appears when it has activity, and its Next line says it is parked.
4. The project line lists its ticket keys after the dash, most active first, at most 4; the parent key is not listed. Keys only, never titles, never PR numbers.
5. Done: one sentence covering the meaningful work since the last standup. Something shipped, merged, approved, decided, designed, built or delivered. Join two or three things with commas; never a second Done line. Drop acks, nudges, draft discards and routine checks unless the project has nothing else. No PR numbers, commit hashes, Slack timestamps, file paths or clock times.
6. Live: one sentence on what is now live for customers, only when a change on that project reached production since the previous rollover (a prod deploy, a prod backfill or config change the user applied), taken from PREVIOUS DONE TODAY and the reports' "Activity since" and "Posts sent since" sections. The Done line still covers the same work; merged-but-not-deployed work stays in Done only. Omit the line when nothing deployed.
7. Next: one spoken sentence, from TODAY'S GOAL first (in goal order), then the CARRIED NEEDS-YOU lines for that project. Not a copy of the goal text.
8. Waiting on: at most one line per project, from BLOCKED and CARRIED NEEDS-YOU rows that wait on another person for that project. Pick the one that gates the Next line. Omit the line when nothing is waiting.
9. Oncall: only lines of PREVIOUS DONE TODAY whose text after the checkbox starts with `oncall:` (drop the prefix). Nothing else goes here: not alert channels, monitors, error trackers or dependency alerts. No such lines, no Oncall heading.
10. Say this: write it last, from the finished By project block. One sentence per project, same order, naming the people from the Done and Waiting on lines by first name, and saying what went live when a project has a Live line. Plain English a non-engineer follows.
11. Plain English, short sentences, no em-dashes or en-dashes, no tables, no links, and no PR numbers in any section. Keep acronyms as the inputs write them; never guess what one stands for. Avoid the characters < > [ ] | in text.

PROJECTS (name, priority, ticket keys; may be empty):
{{projects}}

PREVIOUS DONE TODAY:
{{prev_done_today}}

TRACKER REPORT:
{{tracker_report}}

GITHUB REPORT:
{{github_report}}

SLACK REPORT:
{{slack_report}}

TODAY'S GOAL:
{{confirmed_goal}}

CARRIED NEEDS-YOU:
{{carried_needs_you}}

BLOCKED:
{{blocked_rows}}
```

## Peer session handoff (SendMessage, only on rollover or `--sessions`)

```
Status handoff request from the master session. Reply read-only, no actions, under 25 lines, via SendMessage to "{{master_session_name}}": (1) what you are working on and its current state, (2) the next concrete step, (3) anything waiting on {{user_name}} (decisions, approvals, drafts to send), (4) anything blocked and on whom, (5) uncommitted or unpushed work you own (paths).
```

---

## Planner (model: opus, general-purpose, name `<TICKET>-planner`)

```
You are planning ticket {{ticket}} in the worktree at {{worktree_path}} (repo {{repo}}, branch {{ticket}}). The Agent tool cannot set your working directory: every command must use `git -C {{worktree_path}}` or `cd {{worktree_path}} && ...`, and every file path you read or write must be absolute under {{worktree_path}}.

Steps:
1. Invoke the `superpowers:using-superpowers` skill, then run `/start-ticket {{ticket}}` with these overrides of its Step 4:
   - Write the plan to ~/.claude/plans/{{ticket}}.md.
   - Run `/self-review plan` on it and fold the findings in.
   - SKIP the plan-gate marker command at the end of /self-review (it would unlock the master session's plan gate, not this worktree's).
   - Do NOT call ExitPlanMode. Do NOT edit any file in the repo.
2. Return: the plan path, a summary of at most 10 lines, the test strategy in 3 lines, and the open questions for the user.
```

## Implementer (model: opus, general-purpose, name `<TICKET>-impl`)

```
You are implementing ticket {{ticket}} in the worktree at {{worktree_path}} (repo {{repo}}, branch {{ticket}}) from the approved plan at ~/.claude/plans/{{ticket}}.md. The Agent tool cannot set your working directory: use `git -C {{worktree_path}}` or `cd {{worktree_path}} && ...` in every command and absolute paths under {{worktree_path}} for every edit.

Rules:
- Invoke `superpowers:executing-plans` and follow the plan task by task.
- Write tests alongside the code. Do NOT run the test suite or the linter; CI verifies (unless the plan says the user asked for a local run).
- Do NOT commit, push, stash or checkout.
- Do NOT stage or touch .gitignore, lock files, CLAUDE.md or AGENTS.md changes the worktree setup left behind.
User notes from approval: {{approval_notes}}

Return: `git -C {{worktree_path}} status --short`, a diff summary per file (what changed and why), tests added, and anything in the plan you could not do.
```

## Reviewer (model: opus, general-purpose, name `<TICKET>-review`)

```
You are a fresh reviewer for ticket {{ticket}}, implemented in the worktree at {{worktree_path}} (repo {{repo}}, branch {{ticket}}). You have not seen the conversation. Use `git -C {{worktree_path}}` for every git command.

Nothing is committed yet, so review the WORKING TREE, not the branch: `git -C {{worktree_path}} diff HEAD` plus the untracked files listed by `git -C {{worktree_path}} status --short` (read each one).

1. Read the ticket ({{ticket_url}}) and the plan at ~/.claude/plans/{{ticket}}.md.
2. Run `/self-review implementation` on that working-tree diff against the plan and the ticket's acceptance criteria. Skip the plan-gate marker.
3. Do not run `/code-review` here; the `/pr` step runs it on the real PR.
4. Do NOT edit, commit or push anything.

Return only problems, each marked must-fix or recommend: file, line, one-sentence defect, failure scenario, confidence. If nothing was found, say what you checked.
```

## PR agent (model: opus, general-purpose, name `<TICKET>-pr`)

```
You are finalizing ticket {{ticket}} in the worktree at {{worktree_path}} (repo {{repo}}, branch {{ticket}}). Use `cd {{worktree_path}} && ...` for every command.

The user has approved committing and pushing exactly these files: {{approved_files}}. That approval covers the commit and the push only. Do not stage lock files, .gitignore, or worktree setup noise (CLAUDE.md, AGENTS.md, .claude/ changes).

Run `/pr --review-effort medium`. It commits with the CLAUDE.md commit format, pushes, opens the PR from the repo template, runs the background self code review, and watches CI. Never merge. If the self review or CI produces fixes, do NOT apply them and do NOT invoke `/babysit-pr`: report the combined list (CI failures grouped by cause, review findings with file and line) and stop. The master session asks the user and dispatches a fix pass.

Return: commit SHA and message, PR number and URL, final CI state, self review findings and what was applied, and next steps.
```
