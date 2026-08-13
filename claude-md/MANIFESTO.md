# MANIFESTO.md — The Ten Laws (template)

A design-philosophy manifesto for any repo where coding agents (Claude Code, etc.) do real work. `CLAUDE.md` tells the agent **what** to do; this file tells it **how to think** when no rule covers the situation.

**How to adopt:**

1. Copy this file to the target repo root as `MANIFESTO.md`.
2. Replace every `> FILL IN:` block with a real example from that repo — one concrete file, script, or pattern per law. Agents imitate examples far better than prose; a law without a repo example is half a law.
3. Paste the one-liner block (bottom of this file) into the repo's `CLAUDE.md` so the laws load every session.

The test behind every law is Ousterhout's question: **does this change make the system easier or harder to understand?** Complexity compounds — each obscure dependency, clever indirection, or "temporary" workaround makes every future change (by human or agent) slower and riskier. These laws exist to keep the marginal cost of change flat as the codebase grows.

---

## 1. Complexity is the enemy

Every change must leave the system easier to understand than it found it. Complexity arrives in two forms: **dependencies** (code you can't change without understanding code elsewhere) and **obscurity** (important information that isn't visible where you need it). Before you finish any change, ask: did I add either? If yes, the change isn't done.

> FILL IN: a place where this repo collapsed scattered complexity into one entry point (a wrapper script, a single client factory, a consolidated config).

## 2. Imitate before you invent

Search for the existing pattern and copy it. A new pattern is a design decision that requires justification — it is never the default. Agents and humans both learn a codebase by imitation; every one-off variant you introduce becomes false training data for the next reader.

> FILL IN: the canonical patterns in this repo (where validators live, how API clients are constructed, which component library is law). Name the thing an agent must never hand-roll.

## 3. Locality of behavior

Code lives on the thing that does the thing. Reading one file should tell you what it does without chasing five imports. The most dangerous coupling defeats local reasoning — a file that looks self-contained but silently depends on a convention defined elsewhere. When behavior must live elsewhere, leave a visible pointer at the call site.

> FILL IN: this repo's co-location conventions (tests next to source, one component per file, styles with components).

## 4. Deep modules

The best module has a simple interface hiding real work — never the reverse. If callers must understand a module's internals to use it safely, the boundary has failed and the complexity has leaked into every call site.

> FILL IN: this repo's best deep module — the one-call interface that hides a genuinely hard mechanism.

## 5. YAGNI, ruthlessly

Build the minimum thing that solves the problem, not the generalized version of it. No abstraction until the third real use. Speculative generality is complexity paid for today against a need that may never arrive — and it is the single most common way well-meaning contributors feed the complexity demon.

> FILL IN: what is explicitly out of scope right now, so nobody builds "hooks for later."

## 6. Small blast radius

Keep every unit of change small enough to hold in one read. Cap PR size (a good default: ≤10 files / ≤400 net LOC) and keep files readable in a single pass (~300 lines). A file that keeps growing is telling you it has more than one job — split it along the boundary it's already showing you.

> FILL IN: this repo's PR sizing rule and where it's documented.

## 7. Machines enforce invariants, memory doesn't

A rule that lives only in prose will eventually be broken — by a tired human or a context-limited agent. When you find an invariant enforced only by convention, promote it: a lint rule, a database constraint, a CI gate, a permission deny. Prose explains; machines enforce.

> FILL IN: invariants this repo enforces mechanically (lint rules, CHECK constraints, CI gates, denied commands).

## 8. Define errors out of existence

Design interfaces so the wrong thing cannot be expressed, rather than detecting and handling it afterward. Every error path you make impossible is validation code you never write, a test you never need, and an incident that never happens.

> FILL IN: an interface in this repo where the dangerous form simply doesn't exist (a required explicit target argument, a type that can't represent the invalid state).

## 9. Verify, then claim

Nothing is "done" until lint, typecheck, and tests say so — run them, read the output, then say it. Speed without verification is technical debt with better marketing, and an unverified claim of success is worse than a reported failure.

> FILL IN: this repo's quality gates and the exact commands to run them.

## 10. Leave a trail

The codebase is the training data for every future session — human or agent. Choose names that grep well. Put documentation where the next reader will actually look (next to the code, or in the runbook they'll reach for during an incident). Never bury a critical fact in a place only you would think to check.

> FILL IN: where operational and architectural knowledge lives in this repo, and confirm `CLAUDE.md` points at it.

---

## When laws collide

Lower-numbered laws win. Simplicity (1) beats consistency with a bad pattern (2); an enforced invariant (7) beats a documented one (10). If a collision feels genuinely unresolvable, that's a design smell — surface it to a human instead of picking silently.

_Lineage: John Ousterhout's [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php), [The Grug Brained Developer](https://grugbrain.dev/), and the emerging agent-first codebase literature._

---

## CLAUDE.md snippet (copy-paste)

```markdown
## The Ten Laws

**Design philosophy for every change. Full reasoning and repo examples: `MANIFESTO.md`. Lower-numbered laws win on collision.**

1. **Complexity is the enemy** — every change must leave the system easier to understand.
2. **Imitate before you invent** — copy the existing pattern; a new pattern needs justification.
3. **Locality of behavior** — code lives on the thing that does the thing.
4. **Deep modules** — simple interfaces hiding real work, never the reverse.
5. **YAGNI, ruthlessly** — build the minimum thing; no abstraction until the third real use.
6. **Small blast radius** — small PRs; files readable in one pass.
7. **Machines enforce invariants** — promote conventions to lint / constraints / CI; prose explains, machines enforce.
8. **Define errors out of existence** — make the wrong thing inexpressible, don't handle it after.
9. **Verify, then claim** — nothing is done until lint, typecheck, and tests say so.
10. **Leave a trail** — grep-friendly names, docs where the next reader will look.
```
