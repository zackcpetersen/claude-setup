# model-discipline

A Claude Code plugin that keeps expensive-model spend on judgment work. It is part of the [claude-setup](https://github.com/zackcpetersen/claude-setup) repo and installs through that repo's plugin marketplace.

## What it does

- **A PreToolUse guard on the `Agent` tool.** On a session running an expensive model, it denies subagent dispatches that omit `model` when the agent's own definition has no `model:` pin - an unpinned dispatch silently inherits the expensive session model. It fails open on every error path, so it cannot break dispatching.
- **A sub-agent rules appender on the `Agent` tool.** For write-capable dispatches (`general-purpose`, `claude`, or no type) it appends a `## Sub-agent rules` block to the prompt: use your own environment, batch changes into one push, deliver the report once as `DONE:` or `BLOCKED:` (by the hand-back tool or as the final message, never also by SendMessage), re-read a plan file's `## Decisions` before reporting, one owner per file or page. Read-only types (Explore, Plan and the like), forks, and prompts that already carry the heading are left alone. It fails open, so a broken hook never blocks a dispatch.
- **A context warning (PostToolUse, every tool).** When the main session's context passes `CLAUDE_CONTEXT_WARN_AT` tokens (default 400000; `0` or `off` turns it off), it tells the session once to write the handoff and ask for `/clear` at the next pause. It re-arms when the context drops below the line. Sub-agents (inputs with an `agent_id`) are skipped.
- **A code-review target guard (PreToolUse on `Skill` and `Agent`).** Denies `/code-review` with a bare PR number (`123` or `#123`), which resolves against the current directory's repo, and asks for the full PR URL. Placeholder text passes.
- **A short rules block at SessionStart.** Four lines on dispatch models, keeping tool-heavy loops and browser verification out of the main loop, and preferring `/clear` plus a handoff over repeated `/compact`, plus the sub-agent rules for the coordinating session.
- **A `playbook` skill** (`/model-discipline:playbook`) with the full reference: the dispatch ladder, when a top-model subagent is justified, pin upgrade/downgrade rules, the `fork` caveat, why the session rules matter, and the pattern for setting a repo up so agents pick the right model on their own.

## Install

From GitHub:

```
/plugin marketplace add zackcpetersen/claude-setup
/plugin install model-discipline@claude-setup
```

From a local clone (for testing your own edits):

```
/plugin marketplace add ~/Projects/claude-setup
/plugin install model-discipline@claude-setup
```

Restart Claude Code afterwards - hooks load at session start.

Both registrations use the marketplace name `claude-setup`, so run `/plugin marketplace remove claude-setup` before switching between the local path and GitHub.

**If you previously hand-wired `agent-model-guard` into `~/.claude/settings.json`, remove that `hooks.PreToolUse` entry.** A plugin hook and an identical settings.json hook both fire, so you would get the guard twice.

The same two steps from a plain shell, for scripts or an agent doing the setup for you:

```bash
claude plugin marketplace add zackcpetersen/claude-setup
claude plugin install model-discipline@claude-setup
```

## Configuration

`CLAUDE_EXPENSIVE_MODEL_PREFIX` sets which session model the guard polices. It defaults to `claude-fable`; set it to `claude-opus` if opus is your top tier.

`CLAUDE_CONTEXT_WARN_AT` sets the context warning line in tokens (default `400000`; `0` or `off` turns it off).

## What it does not do

It cannot set your session model - that is a user-settings value no plugin can control. Put `"model": "claude-fable-5-1[1m]"` in `~/.claude/settings.json` yourself, or use `claude --model` / `/model`.

The guard is a backstop, not a wall. It fails open when `jq` is missing, when the transcript cannot be read, when no assistant entry appears in the last 200 lines of the transcript, and for namespaced plugin agent types. The written rule in your `CLAUDE.md` is the primary carrier; subagents never see SessionStart-injected context.

## Verify it is running

- `/plugin list` shows `model-discipline` enabled.
- A fresh session's context includes the model-discipline rules block.
- On an expensive session, an `Agent` dispatch with no `model` is denied with the guard's message; `model: "sonnet"` goes through.
- `bash plugins/model-discipline/tests/agent-model-guard.test.sh` prints `5/5 passed.`
- `bash plugins/model-discipline/tests/agent-rules-append.test.sh` prints `7/7 passed.`
- `bash plugins/model-discipline/tests/context-warn.test.sh` prints `8/8 passed.`
- `bash plugins/model-discipline/tests/review-target-guard.test.sh` prints `8/8 passed.`

## Iterating locally

Installed plugins are cached copies under `~/.claude/plugins/cache/`, not live links, so editing the repo does not change what is running. Either:

- run `claude --plugin-dir ~/Projects/claude-setup/plugins/model-discipline` to load the working tree directly, or
- run `/plugin marketplace update claude-setup` and reinstall after each edit. Bump `version` in `plugin.json` on every pushed change, or the reinstall is a no-op.
