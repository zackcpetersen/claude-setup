# Board config

### Work board (`board` skill)
<!-- FILL IN: every value the board skill needs. Delete this section if you do not use it. -->
- Board page: <Notion page URL or id; the page holds one inline database>
- Slack user id: <U0XXXXXXX>
- Watched channels: <#project-channel C0XXXXXXX, #alerts-channel C0XXXXXXX (alerts), ...> <!-- tag alert channels with (alerts) so the board also scans them for unhandled alerts -->
- Tracker project: <PROJ>; epics to roll up: <PROJ-100, PROJ-200>
- GitHub org: <org-name>
- Worktree config: ~/bin/.worktree-config.json; scripts: ~/bin/worktree, ~/bin/start-ticket
- Memory dir: <path to the Claude memory directory for this machine>
- Watch-slack state file: ~/.claude/watch-sweep.json <!-- holds the declined list for the board's NUDGE? and PROPOSE questions; the main session writes it -->
- WIP limits (starting values, tune after a week): max_streams 3, max_needs_you 7, carry_flag_days 3
- Projects data source: <collection://... of the Projects database, optional> <!-- one row per workstream; the board appends progress and decisions to its pages -->
- Oncall: <yes|no> <!-- flip at the start of each rotation week; `no` means the board never reads alert channels or tracks alerts -->
- Access checks: per-machine list in `~/.claude/auth-checks.json`, run by the `daily-auth` skill (start from `skills/daily-auth/auth-checks.example.json`)
