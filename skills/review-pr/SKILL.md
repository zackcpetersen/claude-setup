---
name: review-pr
description: Use when the user asks to review, code-review, or approve someone else's pull request by number or URL, or to leave review comments on a PR. Not for the user's own PRs (that is /pr's self review).
---

# Review PR

Review a teammate's pull request the way a careful colleague would: find what matters, say it as a question or a suggestion, skip the noise, and approve when nothing blocks. The review itself runs in a background opus agent via the built-in `/code-review` skill; the main session triages, gets the user's approval per comment, and posts one GitHub review.

## Usage

`/review-pr <PR number or URL> [--effort low|medium|high|xhigh|max] [--repo owner/name]`

Default effort `medium`. The repo comes from the URL, from `--repo`, or from the current directory's `origin`.

## Config

- Voice: if `~/.claude/CLAUDE.md` has a `### Writing voice` section, invoke the skill it names (and fetch its voice page) before drafting comments. Otherwise use the voice rules in `dispatch-prompt.md`.
- Tracker: the `### Issue Tracker` section gives the ticket URL format, used only to read the linked ticket for context.
- Posting rule: GitHub review comments have no draft mechanism. The user approves each comment before anything is posted, every time, even when they asked for the review to be posted up front. Show the list, get a yes, then post.

## Procedure

1. **Dispatch the reviewer** (`Agent`, `general-purpose`, `model: opus`) with the prompt in `dispatch-prompt.md`. It runs `/code-review <effort> <PR>` (effort first, never `--comment`, never `--fix`), reads the PR description, linked ticket and existing review threads, and returns a verdict plus drafted comments. It posts nothing. `/code-review` forks its own background reviewer, and that reviewer's findings arrive as a task notification in the main session, not inside the wrapper agent, which goes idle waiting. When that happens, forward the findings to the wrapper with `SendMessage` and let it draft; do not draft in the main session.
2. **Triage** the findings it returns:
   - `high`: would break behaviour, data, security, or cost. Blocks approval. Posted as a normal inline comment.
   - `medium`: worth fixing, does not block. Posted inline prefixed `nit: `.
   - `low`: dropped. Listed to the user in one line each, never posted.
   - Anything an existing review thread already raised is dropped as a duplicate.
3. **Present** to the user: PR summary (3 lines), verdict (APPROVE when there are no highs, otherwise COMMENT), the one-line review body, then each comment as `file:line`, severity, the drafted text. Ask for approval; the user can drop or reword any item, post only the highs, or drop the body (an empty `body` is valid).
4. **Post** one review with every approved comment in a single call, so the author gets one notification:

   ```bash
   gh api repos/<owner>/<repo>/pulls/<n>/reviews --input review.json
   ```

   where `review.json` is `{"event":"APPROVE"|"COMMENT","body":"<review body>","comments":[{"path":"<file>","line":<n>,"side":"RIGHT","body":"<text>"}]}`. `line` is the line number in the new file for `RIGHT`, the old file for `LEFT`. If GitHub rejects a line as outside the diff, fall back to the nearest changed line in that hunk and say so.
5. **Verify** with `gh pr view <n> --json reviews,reviewDecision` and report: review id, event, comment count, and the PR link.

## Comment rules

- Questions and suggestions, never verdicts. "Could this double-count when the account changes inside the window?" not "This double-counts." The reviewer may be wrong, and a question invites the author to explain.
- One to three short sentences, plain English, acronyms spelled out on first use.
- `nit: ` prefix on every medium.
- No em-dashes or en-dashes, plain hyphens only. No "honestly", "genuinely", "hope", "maybe", "try", "if possible", "might want to consider". No exclamation hype.
- Friendly and collaborative. Direct, not brusque.
- Review body is one line: "LGTM, two small nits inline." or "Two questions inline before I approve, mostly around X." Leave it empty when the user asks for inline comments only.

## Model discipline

Reviewer agent: opus (judgment). The main session never reads the diff itself; it triages the agent's list and talks to the user.

## Common mistakes

| Mistake | Fix |
|---|---|
| Posting before the user has seen the list | The user's "review and post" is the intent; the per-comment yes is the approval. Always show the list first |
| `/code-review 2249 medium` | Effort level goes first. The skill reads its first token as the level |
| Passing `--comment` or `--fix` to `/code-review` | Posting is this skill's step 4, with one combined review; fixes are the author's job |
| Approving with a high finding outstanding | Highs block. Use `COMMENT` and say what needs an answer |
| One `gh pr comment` per finding | One review submission, one notification, inline anchors |
| Reviewing the user's own PR | That is `/pr`'s self review. Stop and say so |
| Stating findings as facts | Turn every comment into a question or a suggestion before presenting it |
| Waiting on the wrapper agent while `/code-review`'s findings sit in the main session | The forked reviewer reports to the main session. Forward its findings to the wrapper and let it draft |
