# Reviewer dispatch prompt

Fill the `<...>` placeholders from the arguments, `~/.claude/CLAUDE.md` and the `reviewing-prs` skill. Paste the named sections in as text; never tell the agent to load a skill. Dispatch with `subagent_type: general-purpose`, `model: opus`, name `pr<N>-review`.

```
Review pull request <N> in <owner>/<repo> (<PR URL>) and return drafted review comments. Do NOT post anything: no `gh pr comment`, no `gh pr review`, no `--comment`, no `--fix`, no commits, no checkouts. The main session posts after the user approves each item.

Steps:
1. Invoke the `code-review` skill as `/code-review <effort> <N>` (effort level first, then the PR number). Never pass `--comment` or `--fix`. If the skill forks a background reviewer, wait for its findings. There may be no local checkout of this branch; use `gh pr view <N> --json ...`, `gh pr diff <N>` and `gh api` for context. <If a local clone exists: "The repo lives at <path>; read-only, use `git -C <path> ...`, never check out or change branches there.">
2. Read the PR description, the linked ticket if any (<ticket URL format>), and every existing review thread so you do not repeat what others already raised.
3. Classify every finding with these triage rules: <Paste the reviewing-prs "Triage" section here.>
4. For each high and medium finding, draft an inline review comment in the author's voice. <Paste the voice rules from the writing-voice skill or voice page here.> Plus these review rules: <Paste the reviewing-prs "Writing a comment" section here.>
5. Decide the verdict with these rules: <Paste the reviewing-prs "Verdict" section here.> Draft a review summary only when the comments need one to make sense; then it is one line in the same voice.

Return under 120 lines in this exact shape:
- PR summary: 3 lines (what it changes, size, CI and existing review state).
- Verdict: APPROVE or COMMENT, one sentence why.
- Review summary text: one line only if the comments need one, otherwise the word "none".
- Comments: a numbered list; each item has `file`, `line` (new-file line number from the diff, and the `side` RIGHT/LEFT), `severity` high|medium, `finding` (one sentence, for the user), `comment` (the drafted text to post verbatim).
- Dropped lows: one line each, finding only, no drafted text.
- Code review effort used and total findings count.
```
