Model discipline (model-discipline plugin): pass `model` on every Agent dispatch (sonnet = mechanical, opus = implementation/exploration/review) unless the agent definition pins one; fork always runs on the parent model.
Reserve the top session model for judgment.
Tool-heavy loops and browser verification run in subagents, never the main loop.
Prefer /clear + handoff over repeated /compact; truncate large command output. Full playbook: /model-discipline:playbook.

## Sub-agent rules
- Own environment: unset `VIRTUAL_ENV` and use the worktree's own env, never the main checkout's venv.
- Batch changes into one push, not a push per fix.
- Report exactly once at the end: `DONE: <summary or sha>` or `BLOCKED: <reason>`.
- One owner per file or Notion page: never edit what another agent owns.
- Coordinator: check on any agent silent for more than 10 minutes and unblock it.
