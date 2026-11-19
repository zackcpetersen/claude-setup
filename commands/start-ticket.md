---
name: start-ticket
description: Fetch ticket context from your issue tracker and create an implementation plan
---

# Start Ticket Skill

## Input

**Arguments**:
- `{ticket}` - Required: a ticket key (e.g., `PROJ-123`), or in a no-ticket repo a short name (lowercase words joined by hyphens, for example `workflow-and-self-review`)

If no ticket argument provided, error with usage:
```
Usage: /start-ticket <ticket-number>
Example: /start-ticket PROJ-123
```

## Execution Steps

### Step 1: Get Ticket Context

In a no-ticket repo (the `No-ticket repos` line of CLAUDE.md), skip this step: take the requirements from the user's request and any files they named, and say "no ticket (no-ticket repo)". A repo matches by the folder name of its main checkout (`basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"`), so worktrees match too.

Use the issue tracker MCP tools named in CLAUDE.md's Issue Tracker section to fetch and display:
- Ticket summary and description (get issue details)
- Acceptance criteria
- Any linked tickets or dependencies
- Comments with additional context

Present the ticket details in a readable format.

### Step 2: Create Implementation Plan

Based on the ticket requirements:
1. Explore relevant areas of the codebase
2. Identify files that need modification
3. Design an implementation approach
4. Write the plan to the plan file (the path Claude Code names when plan mode starts)
5. List the repo rules that apply (the `self-review` Repo rules check: CLAUDE.md, AGENTS.md, matching repo skills, header and never/only comments of each file the plan touches) and say how the plan follows each.
6. Every fact the plan relies on cites a file:line in the checkout being planned. Search only that checkout.
7. Slice the work into PRs of 500 changed lines or fewer (generated files excluded), or say why not.

### Step 3: Define Test Strategy

As part of the plan, include a **Test Strategy** section. Determine what testing is needed based on the ticket's scope and include it in the plan file.

The test strategy should cover:
- **Unit/integration tests** to add or update
- **Manual verification steps** to confirm the change works end-to-end
- **Test data setup** needed (e.g., finding a suitable existing record)

Include the verification tools and skills listed in CLAUDE.md's Available Tools section (database query helper, log search, E2E test skills) when they apply to the ticket. If CLAUDE.md lists none, fall back to the repo's test command from the Repo Conventions table.

Only reference skills that are relevant to the specific ticket - not every ticket needs all of them.

### Step 3b: Decisions

The plan file has three sections the session keeps current:
- `## Decided by default`: reversible choices taken with the recommended option, one line each, for the user to overrule.
- `## Open questions`: only questions that pass the question gate in CLAUDE.md (sends, merges, prod runs, money, scope, timeline, anything hard to undo). All of them are asked in the one plan-approval ask.
- `## Decisions`: answers the user gives later. The session writes them here; agents working from the plan re-read this section before they report.

### Step 4: Self-review, then Exit Plan Mode

Run `/self-review` on the plan first (CLAUDE.md's Plan Review rule) and fold in its findings. Then use `ExitPlanMode` to present the plan for user approval.

## Error Handling

- If ticket doesn't exist (ticketed repos only): Stop immediately with clear error message
- If the tracker API fails: Report the specific error and stop

## Example Session

```
User: /start-ticket PROJ-123

Claude: Let me fetch the ticket and create an implementation plan.

[Uses the tracker's MCP tools to fetch ticket details]
[Displays ticket summary, description, acceptance criteria]
[Explores codebase and identifies relevant files]
[Creates implementation plan in plan file]
```