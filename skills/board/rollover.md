# Board: rollover

Read SKILL.md first; this file holds only the rollover steps.

## rollover

Run the access check first (SKILL.md). Then dispatch `board-writer` once in `rollover` mode (SKILL.md, Dispatching agents) for the row creation and the carry in this paragraph, with the access check's needs-user lines in its inputs; it returns the carried Needs-you, the unmet outcomes with reasons, deadlines and meetings it saw, in under 40 lines, which the main session uses to propose the goal. The writer creates today's row (`Name` = `YYYY-MM-DD (Day)`, Date, Status Open) and its scratchpad child. If a row with today's Date already exists (the user pre-created it to park items for today), reuse it: set its Status Open, keep every line already on it, and merge the carried items in under the matching headings instead of creating a second row. Into Your view copy unchecked Needs-you, non-done In-flight, all Blocked and Deferred lines, Loose ends lines (when Loose ends is a daily-row section, see the `tidy` skill), and every Delivered, not confirmed line unchanged (the delivered date stays the original); append ` (since YYYY-MM-DD)` to each carried line that lacks one, using the previous row's Date (the carry flag compares that date to today). Into the new scratchpad copy every Work registry row whose stage is not done, the Peer sessions table, and the open outreach thread list from Raw findings. Write the Rollover log on both pages, starting with `Rollover started: <UTC time this rollover began>`, then listing each unmet goal outcome from the previous row with a one-line reason. Set the previous row Closed. Then the main session runs the `tidy` skill in `stale` mode (only with `~/.claude/config/tidy.md` or a `### Tidy` section); its findings go to the Open questions queue, not a separate ask.

Then set the goal: propose outcomes for today, three by default and never more than five, drawn from unmet outcomes, carried Needs-you lines, nudges due today, meetings the user must attend and dated deadlines, each one something the user can finish today. Ask the user to confirm or edit before writing it. When tidy's scan says `weekly_due`, the same grouped question also asks "Run the weekly tidy now or at today's wrap?" (the goal and that ask are the one place rollover waits on the user); "now" runs it after the sync, "at wrap" is written to the scratchpad as `Tidy weekly: at wrap`. Write the confirmed outcomes under Today's goal and the same outcomes in one line in the Focus property, with a second one-shot writer dispatch (edit mode). Then sync; its step 4 builds the standup. After that sync, start the Slack poll if config says `Slack poll: on` and it is not already running (see the `watch` skill).


## Common mistakes (rollover)

| Mistake | Fix |
|---|---|
| Two rows left Open after a crash mid-rollover | Keep the newest, close the rest |
| Rollover creates a second row for today | A pre-created row for today (parked items) is reused, never duplicated |
| Building the standup from the board's Done-today ticks alone, or re-running the gatherers for it | Ticks miss untracked work (merges, approvals, replies). Feed it the gatherer replies this rollover already has |
| Rewriting Today's goal during sync, or setting it without the user | The goal is set once at rollover with the user's confirmation; sync only ticks outcomes and logs confirmed swaps under Changes |
