Model discipline (model-discipline plugin): pass `model` on every Agent dispatch (sonnet = mechanical, opus = implementation/exploration/review) unless the agent definition pins one; fork always runs on the parent model.
Reserve the top session model for judgment.
Tool-heavy loops and browser verification run in subagents, never the main loop.
Prefer /clear + handoff over repeated /compact; truncate large command output. Full playbook: /model-discipline:playbook.

## Sub-agent rules
- Own environment: unset `VIRTUAL_ENV` and use the worktree's own env, never the main checkout's venv.
- Batch changes into one push, not a push per fix.
- Deliver your report once: `DONE: <summary or sha>` or `BLOCKED: <reason>`, by the hand-back tool when you have one, else as your final message. Never also send it with SendMessage.
- One owner per file or Notion page: never edit what another agent owns.
- Coordinator: check on any agent silent for more than 10 minutes and unblock it.
- Agent reports arrive once. An idle notice from an agent whose report you already handled gets no reply, no tool call and no narration. Never report a notice older than that agent's latest report as status.
- Answers for an agent that works from a plan file go into that file's `## Decisions` section, not a SendMessage; it reads them before it reports. Forwarding findings or information an agent is waiting on (for example a forked reviewer's findings) still goes by SendMessage.
- When the context warning appears, write the handoff and ask for /clear at the next natural pause.
