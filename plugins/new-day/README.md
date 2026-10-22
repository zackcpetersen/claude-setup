# new-day

A Claude Code plugin that makes sure the day's logins get checked before other work. It is part of the [claude-setup](https://github.com/zackcpetersen/claude-setup) repo and installs through that repo's plugin marketplace.

## What it does

- **A UserPromptSubmit hook.** On every prompt, it reads `~/.claude/daily-auth-last-run.json`. Until that file's `date` is today, it adds a one-line note to the prompt telling Claude to run the `daily-auth` skill first (board rollover runs it too). Once the skill writes today's file, the hook goes quiet until tomorrow.
- It checks every prompt, not just the first one of a session, because sessions often stay open across days.
- It skips prompts no human typed: task notifications, `/loop` ticks, scheduled tasks, and messages from other sessions or subagents.

It is a pure file read and date compare: no network, well under a second. It fails open, so a missing `jq` or bad input never blocks a prompt.

## The skill lives elsewhere

The `daily-auth` skill itself is in `skills/daily-auth/` and is symlinked by `install.sh`, not shipped in this plugin. A skill inside a plugin gets a namespaced name (`new-day:daily-auth`) and runs from a cached copy, so edits would not be live. The skill's per-machine list of checks lives in `~/.claude/auth-checks.json` (start from `skills/daily-auth/auth-checks.example.json`).

## Install

From GitHub:

```
/plugin marketplace add zackcpetersen/claude-setup
/plugin install new-day@claude-setup
```

From a local clone (for testing your own edits):

```
/plugin marketplace add ~/Projects/claude-setup
/plugin install new-day@claude-setup
```

Restart Claude Code afterwards - hooks load at session start.

Both registrations use the marketplace name `claude-setup`, so run `/plugin marketplace remove claude-setup` before switching between the local path and GitHub.

The same two steps from a plain shell, for scripts or an agent doing the setup for you:

```bash
claude plugin marketplace add zackcpetersen/claude-setup
claude plugin install new-day@claude-setup
```

## Verify it is running

- `/plugin list` shows `new-day` enabled.
- With yesterday's date (or no file) in `~/.claude/daily-auth-last-run.json`, every prompt carries the "daily-auth has not run yet" note. After `/daily-auth` writes today's date, the next prompt is quiet.
- `bash plugins/new-day/tests/new-day-check.test.sh` prints `9/9 passed.`

## Iterating locally

Installed plugins are cached copies under `~/.claude/plugins/cache/`, not live links, so editing the repo does not change what is running. Either:

- run `claude --plugin-dir ~/Projects/claude-setup/plugins/new-day` to load the working tree directly, or
- run `/plugin marketplace update claude-setup` and reinstall after each edit. Bump `version` in `plugin.json` on every pushed change, or the reinstall is a no-op.
