# Board: wrap

Read SKILL.md first; this file holds only the wrap steps.

## wrap (end of day)

Runs when the user says the day is done ("wrap up", "end of day", "clean up") or on `/board wrap`. It leaves the machine and the board in the state rollover expects the next morning. Nothing here sends, posts or removes a permission rule on its own.

1. **Drafts.** Every draft the session created today is listed in the scratchpad's `## Drafts today` table (id, channel or mailbox, thread, gist, status). Dispatch `drafts-check` (sonnet, Explore, see SKILL.md Dispatching agents) with `scratchpad_url`, not the pasted table: for each draft it reads the target thread, channel or mailbox and reports SENT (UTC time, message ts or id, and first words), SCHEDULED, DISCARDED (superseded drafts must show nothing posted) or NOT FOUND. Update the table and put every NOT FOUND or wrongly posted draft under Needs you.
2. **Repos.** Run the `tidy` skill once, in `weekly` mode when its scan says `weekly_today` or `weekly_due` or the scratchpad says `Tidy weekly: at wrap`, otherwise in `daily` mode. It stops finished agents first, then covers repos and processes. Without tidy config (`~/.claude/config/tidy.md` or a `### Tidy` section), tidy only lists what its merged rule would remove plus dirty worktrees; branches with an open PR are skipped, and nothing is removed.
3. **Processes and tasks.** Covered by step 2's tidy run. List the background shells still running with what they wait on.
4. **Permissions.** List every allow rule added to a settings file today (the session notes them under Your TODOs when it adds one, with the reason). Ask the user which to remove; remove only on a yes.
5. **Agents.** Idle finished agents: covered by step 2's tidy run. A running agent gets one status message and goes under Needs you if it is silent for more than 10 minutes.
6. **Board and handoff.** Tick the goal outcomes that are done, add one `HH:MMZ: wrapped` line under Pacing with goal progress and what carries to tomorrow, refresh the scratchpad's Agents line, and write the handoff file the `## Handoffs` section of `~/.claude/CLAUDE.md` asks for (open PRs with CI and review state, blockers and on whom, unsent drafts verbatim, running waits (the background task ids and commands this session tracks), the exact next command). The handoff holds only today's state: the goal, live agents and waits with task ids, open asks, unsent drafts verbatim, the next command. Standing rules (Notion write rules, wait restart steps, poll triage format) stay in the skills and never go in the handoff. Keep it under 6KB. Hand every board edit from this wrap (step 1's table updates, these ticks and lines) to one board-writer dispatch in edit mode. Then stop the Slack poll (`TaskStop` on its task id); rollover starts it again. After the poll is stopped, and only with tidy config, re-run `~/bin/tidy scan --mode daily --json --no-fetch` and pipe only its `trim_log` finding (if any), as a JSON list, to `~/bin/tidy apply --mode daily`.
7. **Clear.** Every wrap ends by asking for `/clear`, whatever the token count, so the session is never auto-summarized. The session cannot run it itself. The handoff's next command starts with "run the board wrap.md Pickup after /clear check", since the new session reads the handoff, not this file. As the last line, tell the user: run `/clear`, then `read <handoff path> and continue`.

Print: drafts verified (counts and any problems), what was removed, what was left and why, the permission rules awaiting a decision, and the handoff path. Then the step 7 line.

## Pickup after /clear

After any `/clear` (wrap or a mid-day context warning), the new session reads the handoff, then checks that background waits survived: `pgrep -fl wait-for` and `ListAgents`. It restarts the Slack poll if it is gone (see the `watch` skill), except after a wrap, where rollover starts it, and re-arms any wait from the handoff that is missing. A `wait-for` notification can fail to reach the new session after a clear, so a wait whose event may have fired is re-checked directly (`gh pr view`, the thread, the run) instead of trusted as still pending.


## Common mistakes (wrap)

| Mistake | Fix |
|---|---|
| Removing a worktree or branch whose PR is still open, or a dirty one, during wrap | Only branches proven merged (ancestor of origin/default, or PR MERGED with matching head) are removed without a question; everything else is listed or asked |
| Treating a draft as sent because the user said drafts are clear | A cleared draft was sent, scheduled or discarded; wrap reads the target thread to tell which, and a superseded draft must show nothing posted |
| Removing a temporary permission rule during wrap without asking | List it with the reason it was added; the user says which go |
