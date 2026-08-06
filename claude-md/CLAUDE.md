# Global Claude Code Preferences

<!-- Generic user-level CLAUDE.md. Copy to ~/.claude/CLAUDE.md on a new machine
     and fill in the FILL IN sections at the bottom with machine/employer
     specifics. -->

## General Preferences
- Avoid creating new files for notes, summaries, or documentation unless explicitly requested. Provide information directly in the response.
- Prefer separate Bash tool calls over compound commands (&&, ||, ;). Only chain commands when there's a true dependency (e.g., `cd dir && make`).
- When asked to install, run, or fix something - do it directly. Don't autonomously explore the codebase or create plans unless asked. Act first, explain briefly after.
- Do not enter or exit plan mode unless explicitly asked. Deliver results directly in chat.
- Default to the dev environment for all operations unless told otherwise.

## External Communications
- NEVER send external communications (Slack, email, etc.) directly. Always create a draft (e.g. Slack draft, Gmail draft) and link to it for approval before anything goes out.

## Communication Style
- NEVER use em-dashes (—) or en-dashes (–) anywhere, ever. Use plain hyphens (-) instead. Applies to ALL output: chat, code, commits, Slack, tickets, docs, everything.
- Default to plain English and simple terminology. Explain things the way you'd explain them to a smart non-expert.
- "Dumb things down" by default - favor short, clear sentences over jargon-heavy or deeply technical explanations.
- When a technical term is unavoidable, briefly say what it means in everyday language.
- Only go into deep technical detail (internals, edge cases, low-level mechanics, heavy jargon) when I explicitly ask for it (e.g. "explain in detail", "go deep", "be technical").
- If a topic genuinely requires some technical detail to be correct, include the minimum needed and offer to go deeper if I want.
- This applies to ALL written output, not just chat: PR descriptions, commit messages, ticket comments, Slack messages, docs pages, code comments, summaries, etc. Lead with plain-language "what changed and why it matters." Save deep technical detail for when it's asked for or truly required.

## Plan Review
- After drafting any implementation plan, run `/self-review` before presenting. Always include the self-review output so the user can see it was done.

## CI/CD Policy
- Do NOT run tests or linters locally unless explicitly asked. Push and let CI handle verification.
- The "Before Submitting Work" checklist is for final pre-PR review only, not after every edit.

## Git and Version Control
- do not include the claude signature in any commits
- do not commit files until I have approved them
- do not include the claude code signature anywhere
- NEVER commit .gitignore or lock file (poetry.lock, package-lock.json, Gemfile.lock, etc.) changes unless explicitly asked

## Available Tools

These tools are available globally. Use them proactively when relevant - don't wait for the user to invoke the slash command.

### Database Access
Use `~/bin/query_db <env-file> "<sql>"` to query databases (read-only). Credentials live in each repo as gitignored `.env.db.<env>` files at the repo root; run from the repo root, e.g. `query_db .env.db.local "SELECT ..."`. Discover schema via information_schema before querying.
<!-- FILL IN: note per-repo specifics (which .env.db.* files exist, which envs are production) here or in the repo's own CLAUDE.md. -->

### Start Ticket (`/start-ticket`)
Fetches ticket context from the issue tracker and creates an implementation plan. Usage: `/start-ticket <ticket-number>`

### Finalize PR (`/pr`)
Commits changes and creates pull requests. Handles commit message formatting (`[TICKET] type: description`), branch management, and PR creation using the repo's PR template.

<!-- FILL IN: add sections for any other machine-specific tools here (log search, ticket tracker MCP, etc.) -->

## Repo Conventions

<!-- FILL IN: one row per repo you work in regularly -->

| Repo       | Default Branch | Test Command   | Lint Command   |
|------------|----------------|----------------|----------------|
| myrepo     | `main`         | `<test cmd>`   | `<lint cmd>`   |

### Before Submitting Work
1. Run tests and linter for the relevant repo
2. Fix any failures before proceeding
3. Self-review:
   - Re-read ticket acceptance criteria - verify each is met
   - Check for leftover debug code, TODOs, or commented-out code
   - Verify no unintended file changes (migrations, lock files, configs)
   - Confirm tests cover the happy path and at least one edge case
4. Commit with message format: `[TICKET] description`
