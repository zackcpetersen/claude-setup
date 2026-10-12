# Board dispatch prompts

Every `{{placeholder}}` maps to a key in the `### Work board` section of `~/.claude/CLAUDE.md`. Fill them in before dispatching. Pass `model` on every dispatch. Gatherers use `subagent_type: Explore`; planner, implementer, reviewer and pr agents use `general-purpose`. Never use `isolation: "worktree"`.

Read-only rule, included verbatim in every gatherer prompt:

> READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes. If a step would need one, report what you would have done instead.

---

## jira-status (model: opus, Explore)

```
You are gathering a read-only status snapshot of {{user_name}}'s issue tracker work ({{tracker_site}}, tools `{{tracker_mcp_prefix}}*`). Today is {{today}}. READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes.

Run these queries (compact view; fields: key, summary, status, priority, issuetype, assignee, reporter, updated, parent, labels, duedate):
1. assignee = currentUser() AND statusCategory != Done ORDER BY priority DESC, updated DESC
2. reporter = currentUser() AND statusCategory != Done AND assignee != currentUser()
3. parent in ({{tracker_epics}}) ORDER BY status
4. project = {{tracker_project}} AND status in ("In Review", "Review") AND updated >= -14d
5. assignee = currentUser() AND statusCategory = Done AND resolved >= -14d
6. watcher = currentUser() AND statusCategory != Done AND assignee != currentUser() AND updated >= -7d

For each In Progress or In Review ticket from query 1, read the description's progress notes and the last 3 comments: next concrete step, blocked on whom or what, and whether anything waits on {{user_name}} (decision, comment, approval). Treat a batch of tickets all updated in the same minute with no comments as not actually updated.

Return under 120 lines:
- Table A: open tickets assigned to {{user_name}}: key, summary, status, priority, epic, updated, next step, blocked-on, waiting-on-user (yes + what / no).
- Table B: open tickets {{user_name}} reported or watches, assigned to others: status, what is expected from them.
- Epic rollups for {{tracker_epics}}: children by status, stalled children (In Progress, no real update 7+ days), unassigned children.
- Dates in the next 30 days, including dates that only appear in ticket text.
- "Things that look off": In Progress with 10+ quiet days, Done here but open elsewhere, unassigned High priority updated in 14 days, epics in the wrong status.
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
4. Dependabot PRs on the main repos that fix an open security alert: count plus the ones that are major bumps.

Part 2, local checkouts:
1. `{{worktree_script}} list`, then every git checkout under the project root named in {{worktree_config}} (main repos and each `*-worktrees/*` dir).
2. Per checkout: branch, `git -C <path> status --short | wc -l` plus top files, unpushed commits (`git -C <path> log --oneline @{upstream}..HEAD 2>/dev/null | wc -l`), last commit date, open PR for the branch.
3. Flag: uncommitted real work (at risk), branches never pushed, stale (PR merged or closed, or no own commits), broken worktrees, files that look like secrets (`.env*` untracked).

Registry rows to check: {{registry_rows}}

Return under 120 lines: Table A open PRs; Table B review/reply owed; named branch states; Table C local checkouts with a suggested disposition (active / at-risk / stale-remove); "Things that look off".
```

## slack-status (model: opus, Explore)

```
You are gathering a read-only snapshot of what is waiting on {{user_name}} (Slack user {{slack_user_id}}) in Slack. Today is {{today}}. READ-ONLY. Never call any tool that sends, posts, drafts, creates, updates, edits, comments, reacts, transitions, commits, pushes, checks out, stashes or deletes. Use only the Slack read and search tools.

Note: the `<@user>` mention search filter is unreliable (it can return all channel traffic). Read the named channels, threads and DMs directly and say which coverage you have.

Gather:
1. Each watched channel in {{slack_channels}}: read since {{since_date}}. For every top-level post or thread that names or is addressed to the user, decide whether the user replied after the ask. List unanswered ones: channel, who, when, one-line ask, thread ts.
2. DMs and group DMs since {{since_date}}: messages from others the user has not answered, with the ask.
3. Outreach threads the user owns (from the previous scratchpad, passed in below): new replies since last sync, who the ball is with, whether a nudge is due (3 business days of silence), whether a nudge already went out.
4. Alert channels in {{slack_channels}}: anything in the last 3 days tagged to the user's area that has no recovery or reply.
5. `from:<@{{slack_user_id}}> after:{{since_date}}`: commitments the user made that are still open.

Outreach threads to check: {{outreach_threads}}

Return under 120 lines with thread ts values on every line: "Waiting on user" (with urgency today / this week / low), "Waiting on others" (per thread: ball with, since, nudge due or sent), "Commitments made since {{since_date}}", "Alerts possibly unhandled", "Things that look off", and a one-line coverage caveat.
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
You are a fresh reviewer for ticket {{ticket}}, implemented on branch {{ticket}} in the worktree at {{worktree_path}} (repo {{repo}}). You have not seen the conversation. Use `git -C {{worktree_path}}` for every git command.

1. Read the ticket ({{ticket_url}}) and the plan at ~/.claude/plans/{{ticket}}.md.
2. Run `/self-review implementation` against the plan and the ticket's acceptance criteria. Skip the plan-gate marker.
3. Run `/code-review medium {{ticket}}` (pass the branch, not "the current diff"). Never pass --fix or --comment.
4. Do NOT edit, commit or push anything.

Return only problems, each marked must-fix or recommend: file, line, one-sentence defect, failure scenario, confidence. If nothing was found, say what you checked.
```

## PR agent (model: opus, general-purpose, name `<TICKET>-pr`)

```
You are finalizing ticket {{ticket}} in the worktree at {{worktree_path}} (repo {{repo}}, branch {{ticket}}). Use `cd {{worktree_path}} && ...` for every command.

The user has already approved these files for commit: {{approved_files}}. Treat that as the file approval `/pr` needs and as a pre-approved item for `/babysit-pr`'s combined fix list, so do not ask again. Do not stage lock files, .gitignore, or worktree setup noise (CLAUDE.md, AGENTS.md, .claude/ changes).

Run `/pr --review-effort medium`. It commits with the CLAUDE.md commit format, pushes, opens the PR from the repo template, runs the background self code review, and babysits CI. Never merge. If anything needs human judgment (merge conflict, requested changes, a fix that is not straightforward), stop and report it.

Return: commit SHA and message, PR number and URL, final CI state, self review findings and what was applied, and next steps.
```
