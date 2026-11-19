# Watch config

### Watches (`watch` skill)
<!-- FILL IN: values for the watch skill and ~/bin/wait-for. Delete this section if you do not use it. Your Slack user id comes from ~/.claude/config/board.md; do not repeat it here. -->
- Time zone: <America/Denver> <!-- IANA name -->
- Business hours: 08:00-18:00 <!-- Monday to Friday -->
- Connectors: slack mcp__plugin_slack_slack__ <!-- Slack tool name prefix; the Slack poll loads only this plugin's server, which keeps each poll under a cent -->
- Slack poll: <on|off> <!-- on means board rollover starts `~/bin/wait-for slack` in the background; this line is the standing yes -->
- Slack poll every: 5m
- Slack poll model: haiku <!-- the cheap model that reads Slack; it collects, the main session decides -->
- Slack poll triggers: mentions, dms, group-dms, user-groups, thread-replies <!-- add `keywords` to also match the Keywords line -->
- Slack poll user groups: <@team-handle, @other-handle> <!-- groups you belong to; the Slack tools cannot list membership, so this line is the source -->
- Slack poll keywords: <your first name> <!-- only used when `keywords` is in the triggers -->
- Slack poll group-dms: aimed-only <!-- aimed-only: a group DM message wakes the session only if it names you, replies in your thread, or you posted there lately; the rest goes to slack-poll-held.jsonl for the board. all: report every group DM message -->
- Slack poll group-dms lookback: 60m <!-- how recently you must have posted in a group DM for its messages to count as aimed at you -->
- Slack poll user name: <your first name> <!-- optional; matched as a whole word in group DMs; leave it out and the poll reads it from your Slack profile -->
- Slack poll ignore: <C0XXXXXXX, U0XXXXXXX> <!-- channels, people or groups to leave out; ids or names; optional -->
- Slack poll quiet: ack, bot, fyi <!-- messages the cheap model tags with these hints go to slack-poll-digest.jsonl and never wake the session; none turns it off -->
- Slack poll state file: ~/.claude/slack-poll.json <!-- cursor and seen list, written by the script; events land in slack-poll-events/, the triage log in slack-poll-triage.jsonl and held group DM messages in slack-poll-held.jsonl next to it -->
- Dagster: https://<org>.dagster.cloud/<deployment>/graphql, env file ~/path/to/.env, token var DAGSTER_CLOUD_API_TOKEN <!-- optional; fill in <org> and <deployment> or delete this line; wait-for reads the token itself and never prints it -->
- Deploy rules: <!-- one line per repo: `workflow <name> on <branch>`, `release-tag`, or `branch <name>` -->
  - <owner/repo>: workflow <deploy> on <main>
