# Reviewer dispatch prompt

Fill the `<...>` placeholders from the arguments and `~/.claude/CLAUDE.md`. Dispatch with `subagent_type: general-purpose`, `model: opus`, name `pr<N>-review`.

```
Review pull request <N> in <owner>/<repo> (<PR URL>) and return drafted review comments. Do NOT post anything: no `gh pr comment`, no `gh pr review`, no `--comment`, no `--fix`, no commits, no checkouts. The main session posts after the user approves each item.

Steps:
1. Invoke the `code-review` skill as `/code-review <effort> <N>` (effort level first, then the PR number). Never pass `--comment` or `--fix`. If the skill forks a background reviewer, wait for its findings. There may be no local checkout of this branch; use `gh pr view <N> --json ...`, `gh pr diff <N>` and `gh api` for context. <If a local clone exists: "The repo lives at <path>; read-only, use `git -C <path> ...`, never check out or change branches there.">
2. Read the PR description, the linked ticket if any (<ticket URL format>), and every existing review thread so you do not repeat what others already raised.
3. Classify every finding: high (would break behaviour, data, security, or cost; blocks approval), medium (worth fixing, does not block; becomes a "nit:" comment), low (drop, unless it is a one-line fix: then treat it as medium).
4. For each high and medium finding, draft an inline review comment in the author's voice. <Paste the voice rules from the writing-voice skill or voice page here.> Plus these review rules:
   - Phrase as a suggestion or a question, never as a statement of fact. "Could this double-count when X?" or "What happens if Y is null here?" or "Suggest moving this into Z so it runs once." Never "This is wrong" or "This will fail."
   - One to three short sentences and under 60 words. Plain English. Spell out an acronym the first time it appears in the comment.
   - Medium comments start with "nit: ".
   - No em-dashes or en-dashes anywhere, plain hyphens only. Never "honestly", "genuinely", "hope", "maybe", "try", "if possible", "might want to consider", no exclamation-heavy hype.
   - Friendly and collaborative, not brusque.
5. Decide: approve (no highs) or comment-only (any high). Do not draft a review summary unless this prompt says the user asked for one; if asked, one line in the same voice, e.g. "LGTM, two small nits inline."

Return under 120 lines in this exact shape:
- PR summary: 3 lines (what it changes, size, CI and existing review state).
- Verdict: APPROVE or COMMENT, one sentence why.
- Review summary text: only if asked for, otherwise the word "none".
- Comments: a numbered list; each item has `file`, `line` (new-file line number from the diff, and the `side` RIGHT/LEFT), `severity` high|medium, `finding` (one sentence, for the user), `comment` (the drafted text to post verbatim).
- Dropped lows: one line each, finding only, no drafted text.
- Code review effort used and total findings count.
```
