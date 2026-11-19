# Tidy config

### Tidy (`tidy` skill)
<!-- FILL IN: values for the tidy skill. Delete this section to turn tidy off; board wrap then only lists leftovers. The handoff folder comes from the Handoffs section; the archive, log and state live in ~/.claude/tidy/. -->
- Weekly: <Fri> <!-- day whose wrap runs the weekly deep clean; a missed run is offered at the next rollover -->
- Extra repos: <~/Projects/other-repo> <!-- repos not in the worktree config whose branches tidy also checks; optional -->
- Report folders: <~/Desktop> <!-- listed in the weekly report only, never changed; optional -->
- Branch age: 30 <!-- days before an unmerged branch is offered -->
- Plan age: 14
- Handoff age: 14
- Memory age: 30
- Loose ends: <Loose ends> <!-- name of the catch-all Projects row, or of the daily-row section without a Projects data source -->
- Loose ends max: 12
- Loose ends age: 14
- Never touch: <paths or globs> <!-- optional -->
