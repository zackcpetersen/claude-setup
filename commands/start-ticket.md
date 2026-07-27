---
name: start-ticket
description: Fetch ticket context from your issue tracker and create an implementation plan
---

# Start Ticket Skill

## Input

**Arguments**:
- `{ticket}` - Required ticket number (e.g., `PROJ-123`)

If no ticket argument provided, error with usage:
```
Usage: /start-ticket <ticket-number>
Example: /start-ticket PROJ-123
```

## Execution Steps

### Step 1: Get Ticket Context

Use your issue tracker's MCP tools (e.g. the Atlassian plugin for Jira, or Linear/GitHub Issues equivalents) to fetch and display:
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
4. Write the plan to the plan file

### Step 3: Define Test Strategy

As part of the plan, include a **Test Strategy** section. Determine what testing is needed based on the ticket's scope and include it in the plan file.

The test strategy should cover:
- **Unit/integration tests** to add or update
- **Manual verification steps** to confirm the change works end-to-end
- **Test data setup** needed (e.g., finding a suitable claim or record)

Include relevant skills or tools when they apply:
- `query_db` — if the ticket involves database changes, migrations, or data validation, include read-only queries to verify data correctness
- Any project-specific E2E testing skills — if the ticket touches features they cover
- Log search tooling — if the ticket is a bug fix or requires verifying runtime behavior after deploy

Only reference skills that are relevant to the specific ticket — not every ticket needs all of them.

### Step 4: Exit Plan Mode

Use `ExitPlanMode` to present the plan for user approval.

## Error Handling

- If ticket doesn't exist: Stop immediately with clear error message
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