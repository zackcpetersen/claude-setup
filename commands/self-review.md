---
description: Self-review a plan or implementation for correctness, failure paths, repo rules, blast radius, tests, and PR accuracy
allowed-tools: Agent, Bash, Read
---

Dispatch a subagent to run this review. The subagent starts fresh -- it hasn't seen the conversation and won't be biased toward the work it's reviewing. Dispatch it with `model: "opus"` (omitting the model on unpinned agent types inherits the session model).

**Review mode:** If `$ARGUMENTS` is provided, treat it as the review scope (e.g., "plan", "implementation", or a specific focus area). Otherwise infer from context -- if there's a diff on the branch, it's implementation review; if there's an unexecuted plan, it's plan review.

**What to pass the subagent:**

The task requirements (ticket description, user request, or spec)
What changed or is proposed (file paths + short summary of the approach)
Any constraints or decisions made during the conversation


The subagent should review against these areas. **Only report problems.** If an area looks fine, skip it entirely. Do the work -- read the actual diff, grep the codebase, check real data. Don't review from memory or assumptions.

**Plan review:** Will this approach work? Check the design before code is written. Focus on correctness, failure paths, repo rules, patterns, blast radius and tradeoffs.
**Implementation review:** Did it actually work? Read the diff, compare against requirements, catch drift between intent and result. All areas apply.

### What to check


**Correctness** -- The most important check. Flag shortcuts that paper over the requirement instead of solving it, solutions that will mask bugs or mislead callers, edge cases being silently swallowed, and anything that produces the right output today by coincidence rather than by design. When a simpler approach exists but solves the problem the wrong way (workaround, bandaid, hack), flag it -- doing things correctly matters more than doing them simply. Ask: "Would I trust this code in 6 months with no memory of the context?"

**Failure paths** -- For every external call, job and status change, answer in writing: What happens when the call raises an error, not only when it returns a failed response, and does that still hold inside a transaction or while a lock is held? What happens when retries run out, and does anything pick up a record left stuck in that state? What happens when the same input arrives again (a resend, a retry, a duplicate event), including after a failure: do unique indexes and dedupe queries treat failed rows the way the sender expects? Does an early return skip a rescue or a cleanup that should run? Is anything left behind (a file, a blob, a row) when a step gives up?

**Repo rules** -- Read the repo's CLAUDE.md and AGENTS.md (and any skills table they list), and open every repo skill whose description matches an area the change touches. Read the header comment of every edited file and every comment in it that says never, only, always or do not. Check the plan or the diff against each one, at plan time and again at diff time: a plan can pass an implementation review and still break a rule. If the change relaxes or rewrites one of these rules, do not edit it silently: find who wrote it (`git log -L` or `git blame` on the rule's lines) and raise it as a question for that person in the plan and in the PR description. If `~/.claude/config/self-review.md` exists, read it and apply the checks it lists for this repo.

**Reuse before writing** -- Before writing a helper, query or utility, grep for an existing one and use it; drop fields, columns and query selections nothing reads yet.

**Patterns** -- Grep for how similar things are already done. Flag deviations from existing conventions (file placement, architecture layers, base classes, registries, utilities).

**Scope and impact** -- Flag files or interfaces being modified that aren't required by the task, cleanup bundled into a feature change, or changes a reviewer would question as unrelated. Also flag downstream consumers, dependent services/jobs, breaking tests, API contract changes affecting frontend or external callers, and affected monitoring/alerts.

**Blast radius** -- End with one line: which environments, tenants or customers, and event or message types this change reaches. For each config, initializer, CI workflow, scheduler, role or permission change, say whether it is limited to the ones that need it; if the wider reach is on purpose, the PR says so.

**Tests** -- Each lock, guard, skip condition and allow-list has a test where it actually triggers, not only a test of the path around it. A rule that depends on a status gets one table test across every status. Fixtures and mocks match the real schema: build payloads from the real schema, a factory or a recorded sample and validate them against the schema when one exists; mocks include every field the code under test reads; hard-coded lookup values are checked against the helper or enum that validates them.

**Tradeoffs and limitations** -- Flag what we're choosing not to handle and whether that's a conscious decision or an oversight. Call out unverified assumptions the approach depends on, known limitations that should be documented or communicated, things that will need revisiting at scale, and alternative approaches that were viable but rejected -- why this one?

Implementation review only, add:

**Script checks** -- Run `~/bin/pr-precheck report --repo <worktree or repo root>` (no tokens, read-only) and include its output. Over the size limit: propose a split or say why not. A stale generated file: flag it with the hint. Each "inside lock" line: confirm it is safe or flag it. `precheck: not run on this tree` on a branch with no PR yet: flag it as must-fix (run `~/bin/pr-precheck fix` once). If `~/bin/pr-precheck` is missing, say so and skip.

**PR description** (when a PR body exists or is drafted) -- Check every factual claim in it and in changed docs against the code: required fields, error cases, rollback steps, which environments. Risk is set to the highest risk of any part of the change. A rule change found by Repo rules is named in the notes, with its author, as a question.

**Review bots** (when a PR is open) -- List every review-bot comment (code review bots, risk checks, linters that comment). Each needs a fix or a drafted one-line reply before anyone is asked to review.

## Output

Append a **Self-review** section. Only list categories where something is wrong or worth double-checking. Each item should clearly state the problem and what to do about it. If nothing was found, confirm what you actually checked so the user can tell the difference between a thorough review and a rubber stamp.

**Self-review** (`/self-review`)**:**
- **Correctness**: The retry logic swallows `TimeoutError` and returns `None`, which callers will treat as "no results found" instead of "something went wrong" -- should raise or return a distinct error.
- **Reuse before writing**: The date-range filtering reimplements a method the base repository class already has - use it.
- **Scope and impact**: Changing the API response contract will break the frontend until it's updated -- coordinate or version the field.

If the review finds issues:

**Plan phase:** fix the plan before presenting. Note what the self-review caught and what changed.
**Implementation phase:** fix the code before presenting. Note what was caught and changed, or flag items that need discussion.

## Plan-gate marker (plan reviews only)

A PreToolUse hook blocks ExitPlanMode unless a self-review has been recorded. After completing a **plan** review (findings applied or none found), unlock the gate by running:

```bash
mkdir -p ~/.claude/plan-reviews && touch ~/.claude/plan-reviews/"$(printf %s "$PWD" | shasum -a 256 | cut -c1-16)"
```

The marker is consumed by the next ExitPlanMode and expires after 2 hours, so each new plan needs a fresh review. Skip this step for implementation reviews.

If the hook is not installed on this machine, the marker is harmless. Install it with `/plugin install plan-gate@claude-setup`.
