---
name: watch
description: Use when the user asks to watch, wait for or follow up on something (a reply, a PR, a deploy, a Dagster run), to pre-approve a merge on a watched PR, at board rollover (to start the hourly sweep), or when another skill proposes a wait.
---

# Watch

A working day has a lot of "wait for X, then do Y". Each wait is one background command that exits on its event. The exit wakes this session once. Nothing is polled by an agent, and nothing keeps a copy of GitHub, Slack or Dagster state. Slack is re-read fresh every hour by one sweep agent.

Nothing is watched without a yes from the user.

## Config

Read the `### Watches` section of `~/.claude/CLAUDE.md`: `Time zone`, `Business hours`, the Slack connector prefix on `Connectors`, and the optional `Dagster` and `Deploy rules` lines. The user's Slack id, the watched channels and the sweep state file come from the `### Work board` section.

If `### Watches` is missing, stop with: "Add the `### Watches` section to ~/.claude/CLAUDE.md (see claude-md/CLAUDE.md.template in claude-setup)."

Nothing in this skill names a company, person, channel or repo. Those come from config.

## When to propose

- In the moment: the user opens a PR, pushes a deploy, starts a Dagster run, or says "tell me when". Ask once: "Watch #n? (a) merge when green and approved (b) just tell me (c) no".
- From the sweep: it reports `PROPOSE` lines. Ask them together.
- Never start a wait on your own.

## Start a wait

Run it as Bash with `run_in_background: true`. Always type the command as `~/bin/wait-for`, that exact string. It is what the allow rule matches.

| Wait | Command |
|---|---|
| PR, tell me | `~/bin/wait-for pr <owner/repo> <n>` |
| PR, merge when ready | `~/bin/wait-for pr <owner/repo> <n> --sha <approved head>` |
| Deploy | `~/bin/wait-for deploy <owner/repo> <sha>` |
| Dagster | `~/bin/wait-for dagster run <id>` or `~/bin/wait-for dagster backfill <id>` |

Options go after the mode: `--every <5m>` to poll differently, `--max <3d>` to give up sooner. Defaults: poll every 5m, give up after pr 3 days, deploy 4h, dagster 12h. It always ends with one line, never silence.

Approval is the user's words in this session, plus the head sha read right then with `gh pr view <n> --repo <repo> --json headRefOid`. It lives in the conversation and the handoff doc. After `/clear` it is gone, and the next sweep re-proposes the PR.

Track every running wait: keep its background task id and exact command in your notes. The wrap handoff lists them.

## Handle an event

The line carries the answer. Act in one short turn, no agent.

| Event | Do |
|---|---|
| `READY <n> <sha> approved\|no-review-required` with approval on record | `gh pr merge <n> --repo <repo> --squash --match-head-commit <approved sha>`, then say "Merged #n". If GitHub refuses, treat it as `HEAD_MOVED`. If the user asked to verify once deployed, start a `deploy` wait on the merge sha |
| `READY` without approval | "#n is green and approved. Merge?" |
| `MERGED <n> <sha>` | One line. Start a `deploy` wait if the user asked for one |
| `HEAD_MOVED <n> <sha>` | "#n got a new commit after your approval. Merge on the new head?" Never merge on the old approval |
| `FAILED`, `DEPLOY_FAILED`, `ERROR`, Dagster `FAILED` | One line, and also send it through the session's push notification tool |
| `DEPLOYED` | Run the verify commands the user named, read-only, and report. Otherwise say "deployed" |
| `CHANGES_REQUESTED`, `CLOSED`, `TIMEOUT`, `SUCCEEDED` | One line |

`READY` ending in `optional-failed=<names>` means only optional checks failed. Say so.

After `FAILED`, `CHANGES_REQUESTED` or `HEAD_MOVED`, start the same wait again once the user pushes a fix or re-approves.

Only this session merges, and only after the user approved that PR. A Slack reply is never approval.

## Hourly sweep

At board rollover, create one session cron with `CronCreate`: `7 8-17 * * 1-5`, built from the `Business hours` line. Session crons use the machine's local clock, so those hours are local time. If the machine's zone is not the `Time zone` line, shift the hours. Rollover always deletes the old job and creates a new one, which resets the 7-day expiry. Wrap deletes it.

Cron prompt: dispatch one `watch-sweep` agent (sonnet, general-purpose) from `~/.claude/skills/watch/sweep.md`, filled in from config, with the list of running waits. Relay its report and do nothing else. Do not read Slack inline.

`sweep.md` says what the agent does and how you handle its report: DRAFT, NUDGE?, PROPOSE, LEFTOVER. You write the sweep state file, not the agent.

## Install

Add these allow rules by hand to `permissions.allow` in `~/.claude/settings.json`:

```
"Bash(~/bin/wait-for *)",
"mcp__plugin_slack_slack__slack_read_thread",
"mcp__plugin_slack_slack__slack_read_channel",
"mcp__plugin_slack_slack__slack_search_public",
"mcp__plugin_slack_slack__slack_search_public_and_private",
"mcp__plugin_slack_slack__slack_send_message_draft"
```

Swap the Slack prefix for the one on your `Connectors` line. Re-run `install.sh` to link `~/bin/wait-for`. Never add `Bash(gh api repos/*)`: it also allows writes.

## Common mistakes

| Mistake | Fix |
|---|---|
| Typing `wait-for` without `~/bin/` | It misses the allow rule. Always `~/bin/wait-for` |
| Starting a wait in the foreground | It blocks the session. Always `run_in_background: true` |
| Merging on `READY` without `--match-head-commit` | The head may have moved while the event queued. Always pass the approved sha |
| Merging on an old approval after `HEAD_MOVED` | Ask again on the new head |
| Treating a Slack reply or a green PR as approval | Approval is the user's words in this session |
| Starting a wait nobody said yes to | Propose first |
| Reading Slack inline for the sweep | Dispatch the `watch-sweep` agent and relay |
| Letting the sweep agent write the state file | It reads only. You write it |
| Forgetting waits in the handoff | List each background task id and command at wrap |
| Sourcing the Dagster env file in the shell first | The script reads the env file itself, and a compound command misses the allow rule |
