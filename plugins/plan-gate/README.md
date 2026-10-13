# plan-gate

A Claude Code plugin that makes every plan pass a `/self-review` before it leaves plan mode. It is part of the [claude-setup](https://github.com/zackcpetersen/claude-setup) repo and installs through that repo's plugin marketplace.

## What it does

- **A PreToolUse hook on `ExitPlanMode`.** `/self-review` records a marker file under `~/.claude/plan-reviews/` when a plan review completes. The hook denies `ExitPlanMode` unless a marker exists for the current project and is under two hours old, then deletes it, so every new plan needs a fresh review.
- The marker is keyed on a hash of the project directory, so one review unlocks one plan in one project.

## Install

From GitHub:

```
/plugin marketplace add zackcpetersen/claude-setup
/plugin install plan-gate@claude-setup
```

From a local clone (for testing your own edits):

```
/plugin marketplace add ~/Projects/claude-setup
/plugin install plan-gate@claude-setup
```

Restart Claude Code afterwards - hooks load at session start.

Both registrations use the marketplace name `claude-setup`, so run `/plugin marketplace remove claude-setup` before switching between the local path and GitHub.

**If you previously pasted the plan-gate snippet into `~/.claude/settings.json`, remove that `ExitPlanMode` entry from `hooks.PreToolUse` before installing.** Both hooks fire: the first one consumes the marker and the second one denies, so plan mode locks.

The same two steps from a plain shell, for scripts or an agent doing the setup for you:

```bash
claude plugin marketplace add zackcpetersen/claude-setup
claude plugin install plan-gate@claude-setup
```

## What it does not do

It does not run the review for you - `/self-review` (in this repo's `commands/`) writes the marker. Without that command installed, every `ExitPlanMode` is denied.

It fails closed: when `jq` is missing or the hook input has no `cwd`, it denies. Disable the plugin from `/plugin` if you need plan mode without a review.

## Verify it is running

- `/plugin list` shows `plan-gate` enabled.
- `ExitPlanMode` without a review is denied with the plan-gate message; after `/self-review` it goes through once.
- `bash plugins/plan-gate/tests/plan-gate.test.sh` prints `6/6 passed.`

## Iterating locally

Installed plugins are cached copies under `~/.claude/plugins/cache/`, not live links, so editing the repo does not change what is running. Either:

- run `claude --plugin-dir ~/Projects/claude-setup/plugins/plan-gate` to load the working tree directly, or
- run `/plugin marketplace update claude-setup` and reinstall after each edit. Bump `version` in `plugin.json` on every pushed change, or the reinstall is a no-op.
