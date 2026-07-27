---
description: Self-review a plan or implementation for pattern violations, unnecessary complexity, scope creep, duplication, correctness shortcuts, and unintended side effects
allowed-tools: Agent, Bash, Read
---

Dispatch a subagent to run this review. The subagent starts fresh -- it hasn't seen the conversation and won't be biased toward the work it's reviewing.

**Review mode:** If `$ARGUMENTS` is provided, treat it as the review scope (e.g., "plan", "implementation", or a specific focus area). Otherwise infer from context -- if there's a diff on the branch, it's implementation review; if there's an unexecuted plan, it's plan review.

**What to pass the subagent:**

The task requirements (ticket description, user request, or spec)
What changed or is proposed (file paths + short summary of the approach)
Any constraints or decisions made during the conversation


The subagent should review against these areas. **Only report problems.** If an area looks fine, skip it entirely. Do the work -- read the actual diff, grep the codebase, check real data. Don't review from memory or assumptions.

**Plan review:** Will this approach work? Check the design before code is written. Focus on correctness, patterns, scope/impact, and tradeoffs.
**Implementation review:** Did it actually work? Read the diff, compare against requirements, catch drift between intent and result. All areas apply.

### What to check


**Correctness** -- The most important check. Flag shortcuts that paper over the requirement instead of solving it, solutions that will mask bugs or mislead callers, edge cases being silently swallowed, and anything that produces the right output today by coincidence rather than by design. When a simpler approach exists but solves the problem the wrong way (workaround, bandaid, hack), flag it -- doing things correctly matters more than doing them simply. Ask: "Would I trust this code in 6 months with no memory of the context?"



**Patterns** -- Grep for how similar things are already done. Flag deviations from existing conventions (file placement, architecture layers, base classes, registries, utilities).



**Simplification** -- Flag steps that could be removed, abstractions with only one use, things being built that already exist in the codebase or persisted data. But never simplify at the cost of correctness -- a correct solution that's a bit more involved always beats a simpler workaround that cuts corners.



**Duplication** -- Flag logic, queries, constants, or code paths that duplicate something already in the codebase. Ignore trivial repetition; flag duplication that means a future change needs to happen in multiple places.



**Scope and impact** -- Flag files or interfaces being modified that aren't required by the task, cleanup bundled into a feature change, or changes a reviewer would question as unrelated. Also flag downstream consumers, dependent services/jobs, breaking tests, API contract changes affecting frontend or external callers, and affected monitoring/alerts.



**Tradeoffs and limitations** -- Flag what we're choosing not to handle and whether that's a conscious decision or an oversight. Call out unverified assumptions the approach depends on, known limitations that should be documented or communicated, things that will need revisiting at scale, and alternative approaches that were viable but rejected -- why this one?



**Reversibility** -- Flag destructive migrations, schema changes that drop data, changes to shared state with no rollback path.


## Output

Append a **Self-review** section. Only list categories where something is wrong or worth double-checking. Each item should clearly state the problem and what to do about it. If nothing was found, confirm what you actually checked so the user can tell the difference between a thorough review and a rubber stamp.

**Self-review** (`/self-review`)**:**
- **Correctness**: The retry logic swallows `TimeoutError` and returns `None`, which callers will treat as "no results found" instead of "something went wrong" -- should raise or return a distinct error.
- **Duplication**: The date-range filtering in the new query reimplements logic that already exists in the base repository class -- use the existing method instead.
- **Scope and impact**: Changing the API response contract will break the frontend until it's updated -- coordinate or version the field.

If the review finds issues:

**Plan phase:** fix the plan before presenting. Note what the self-review caught and what changed.
**Implementation phase:** fix the code before presenting. Note what was caught and changed, or flag items that need discussion.