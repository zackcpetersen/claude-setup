# Board: start

Read SKILL.md first; this file holds only the start, resume and status steps.

## start

1. Guard: refresh every registry row's stage with the `status` derivation below (files and `gh`, not the scratchpad's possibly day-old peer answers), then count streams whose stage is planning, implementing or code-review across this session and peers; refuse at `max_streams` and name what to finish first. Confirm the ticket exists, except in a no-ticket repo (the `No-ticket repos` line of CLAUDE.md), where the repo argument is required and the short name is the key; resolve the repo from the argument or the ticket, else ask.
2. `~/bin/worktree <repo> <TICKET or short name>` (one command, inline). Registry rows, the plan file `~/.claude/plans/<key>.md` and agent names `<key>-planner` use the same key. Rows keyed by ticket stay as they are.
3. Planner (opus, see SKILL.md Dispatching agents). It writes `~/.claude/plans/<key>.md`, self-reviews it, returns a summary. Registry stage: `awaiting-approval`. The plan file holds `## Decided by default`, `## Open questions` and `## Decisions` (see /start-ticket Step 3b).
4. Ask once: approve, revise with notes, or park, with every open question from the plan in the same AskUserQuestion call. This is ask 1 of at most 2 for the ticket.
   Answers that arrive while an agent works go into the plan file's `## Decisions` section (the main session writes them), never into a SendMessage. Mid-flow snags with a recommended, reversible fix are applied and listed under `## Decided by default`; they are reported in the ship-it ask, not asked on their own.
5. Implementer (opus): executes the plan, writes tests, runs `~/bin/pr-precheck fix` once at the end, commits nothing. Stage `implementing`.
6. Reviewer (opus, fresh): reviews the WORKING TREE (`git -C <worktree> diff HEAD` plus untracked files from `status --short`), since nothing is committed yet, with `/self-review implementation` against the plan and ticket. No `/code-review` here; `/pr` runs it on the real PR. It also runs `~/bin/pr-precheck report` and reviews the plan against the repo rules, not only the diff against the plan. One fix loop if must-fix findings. Stage `code-review`. Present the diff summary.
7. Ask once: "ship it", showing the diff summary, the precheck report, every reviewer finding the session will fix by default, and the Decided by default list, with the watch choice in the same call ("after the PR opens: (a) merge when green and approved (b) just tell me (c) no watch"). This is ask 2. The yes covers commit, push, fix pushes for CI failures and recommended findings on that PR, and starting the chosen wait (a merge still needs approval on record as the watch skill says; (a) is that approval, pinned to the head sha the session reads when it starts the wait). Dispatch the pr agent (opus) with that approval. When it reports fixes, dispatch the fix pass without asking and report it in one line; only a dismissed high finding, a GitHub reply, scope or timeline go back to the user. Stage `pr-open` -> `ci` -> `ready-to-merge`. The user merges, or the master merges through a `wait-for pr` started with the user's approval (`watch` skill).
8. Update the registry row and In-flight table on every stage change.


## resume and status

Derive the stage from durable facts first: plan file present, `git -C <worktree> status --short`, `git -C <worktree> log origin/<branch>..HEAD`, `gh pr view --repo <repo> --head <branch>`. Message an agent only if `ListAgents` shows it alive. `resume` dispatches the agent for the derived stage.


## Common mistakes (start)

| Mistake | Fix |
|---|---|
| Expecting a sub-agent to run inside the worktree | The Agent tool has no cwd. Put the absolute worktree path in the prompt; use `git -C <path>` or `cd <path> && ...` in every command |
| Using `isolation: "worktree"` | It skips the `worktree` script's env and dependency setup. Always use the script |
| Planner runs the plan-gate marker command | It unlocks the master session's gate, not the worktree's. The planner prompt says skip it and never call ExitPlanMode |
| Implementer runs the full test suite | It runs `~/bin/pr-precheck fix` once at the end (changed files only); CI runs the rest |
| Storing agent names as the registry key | Agents die with the session. Key rows by ticket; store worktree, branch, plan file, PR |
| Relaying the user's approval to a peer session | Peer sessions treat a relayed go as unapproved, even quoted verbatim. For anything a peer holds (open a PR, send a draft, commit), tell the user to type the approval in that session; the master session relays information only |
