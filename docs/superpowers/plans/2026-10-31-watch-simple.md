# Watch v2 (simple): recipes, not a registry

Repo: ~/Projects/claude-setup. Date 2026-10-31. Supersedes the registry design (`docs/superpowers/specs/2026-10-28-watch-design.md`, `docs/superpowers/plans/2026-10-28-watch.md`).

## Decisions (Zack, 2026-10-31)

- The simple version: delete the registry script and use one-off background waits plus an hourly Slack sweep.
- Merges stay with Claude: it merges only after Zack approves that PR, and only while the head commit is still the one he approved.
- What gets watched: Slack replies, PRs/CI, deploys, Dagster runs. Email and the requests channel are dropped.
- Proposals come both in the moment and from an hourly sweep. Nothing is watched without a yes.
- Frequency: PR, deploy and Dagster checks every 5 min, free; Slack hourly.

## Idea

GitHub, Slack and Dagster already hold the state. Stop keeping a copy of it. A wait is one background command that exits on its event, which wakes the session once. Slack is re-derived fresh every hour by one sonnet sweep.

## Pieces

### 1. `~/bin/wait-for` (Python, ~250 lines, stdlib only)

One script with three modes. It polls, prints one event line, and exits. It runs in the main session as Bash `run_in_background: true`, so idle cost is zero turns.

It is carved out of today's `bin/watch` rather than written fresh. These pieces move over with their tests:
- `load_config` (trimmed to the kept lines) and `parse_deploy_rule`
- `load_env_file`, `gql` and `backfill_state`
- `contains`, the deploy run filter, and `rollup_state`

The registry, cursors, ticks and expiry stay behind and are deleted in PR 2.

- `wait-for pr <owner/repo> <n> [--sha <approved head>]`: every 5 min, `gh pr view --json state,headRefOid,reviewDecision,statusCheckRollup,mergeStateStatus`. It exits on the first of these:
  - `MERGED <n> <merge sha>`
  - `CLOSED <n>`
  - `FAILED <n> <failed check names>`: a required check failed or was cancelled (cancelled counts as failed on purpose, as today)
  - `CHANGES_REQUESTED <n>`
  - `HEAD_MOVED <n> <new sha>`: only with `--sha`
  - `READY <n> <sha> approved|no-review-required`: `state == OPEN`, `mergeStateStatus == CLEAN`, and `reviewDecision` is `APPROVED` or empty (empty means no review is required). CLEAN already accounts for required checks and required reviews, so optional checks never block.

  It keeps waiting on pending, `UNKNOWN` or `BLOCKED`-by-pending states, and when there are no checks yet. `UNSTABLE` (only optional checks failed) counts as READY, with the failed optional names appended.
- `wait-for deploy <owner/repo> <sha>`: reads that repo's rule from the `Deploy rules` config line (`workflow <name> on <branch>`, `release-tag`, `branch <name>`). It ports today's logic:
  - Keep only runs whose conclusion is `success`, `failure` or `timed_out`; cancelled and skipped runs are passed over.
  - Of the newest five of those, the newest whose head contains the sha decides. "Contains" means `gh api compare` says `identical` or `ahead`.
  - Exits `DEPLOYED <sha> <run id or tag>` or `DEPLOY_FAILED <sha> <run id>`.
- `wait-for dagster run|backfill <id>`: polls the Dagster GraphQL status, reading the token from the env file on the `Dagster` config line itself (never printed). Exits `SUCCEEDED` / `FAILED <status>`. A backfill counts as done only when every partition is terminal.
- **Common to all three:**
  - Poll every 5m, with `--every` to override.
  - `--max` defaults: pr 3 days, deploy 4h, dagster 12h. On max it exits `TIMEOUT <what>`, so silence never looks like waiting.
  - Transient `gh` or curl errors are retried. After 3 in a row it exits `ERROR <first line>`.
  - Exit code 0 on every event line, and 2 on a usage or config error.

### 2. Handling an event (main session, no agent)

The event line carries the answer, so Fable acts in one short turn:

- `READY` with Zack's approval on record for this PR: run `gh pr merge <n> --squash --match-head-commit <approved sha>`, so GitHub refuses if the head moved between READY and the merge (for example, when the event queued while Fable was mid-task). Then say "Merged #n". On refusal, treat it as `HEAD_MOVED`. If Zack asked to verify once deployed, start `wait-for deploy` on the merge sha (from `MERGED`, or `gh pr view --json mergeCommit`).
- `READY` without approval: "#n is green and approved. Merge?"
- `HEAD_MOVED`: "#n got a new commit after your approval. Merge on the new head?" Never merge on the old approval.
- `FAILED`, `DEPLOY_FAILED`, `ERROR`, Dagster `FAILED`: one line, also sent through the session's push notification tool (urgent).
- `DEPLOYED` with verify commands Zack named: run them read-only and report. Otherwise "deployed".
- `CHANGES_REQUESTED`, `CLOSED`, `TIMEOUT`, `SUCCEEDED`: one line.
- After a non-terminal event (`FAILED`, `CHANGES_REQUESTED`, `HEAD_MOVED`), re-launch the same wait once Zack pushes a fix or re-approves.

Approval is the user's words in this session plus the head sha read with `gh pr view --json headRefOid` at that moment. It lives in the conversation (and the handoff doc). After `/clear` it is gone, and the next sweep re-proposes the PR.

### 3. Hourly Slack sweep (one sonnet agent)

- **Schedule:** a session `CronCreate` at `7 8-17 * * 1-5`, built from the `Business hours` line. Session crons use the machine's local clock, so SKILL.md says the hours are local time. Rollover always deletes and re-creates the job, which resets the 7-day expiry. Wrap deletes it.
- **Cron prompt:** dispatch one `watch-sweep` agent (sonnet, general-purpose) from `skills/watch/sweep.md` with its config. Relay its report and do nothing else. No inline Slack reading by Fable.
- **The agent, read-only plus drafts:**
  1. Asks to Zack in the Work board's watched channels and DMs since the last sweep, with no reply from him. It follows the board's `slack-status` unanswered-asks procedure (board `dispatch-prompts.md`, around line 94) by reference, not a copy.
  2. Threads where Zack asked something and got a reply since the last sweep. It judges each one MET, PARTIAL or NOT MET.
  3. Zack's open PRs (`gh pr list --author @me`) that are not already being waited on. The main session passes its running wait list in the prompt.
- **For each item, at most 4 per sweep, oldest first:**
  - A reply needed: create a threaded Slack draft (`slack_send_message_draft`) and report `DRAFT <channel> <thread> <draft id> <gist>`.
  - Something to watch: report `PROPOSE <one plain-English line>`.
  - No reply after 1 business day on Zack's own ask: `NUDGE? <thread>`.
  - Extras roll over to the next sweep.
- **State:** the existing Work board `Watch-slack state file` line, repointed to `~/.claude/watch-sweep.json`. No new config line. It holds:
  - `last_sweep`
  - `declined`: keys with dates, either `pr:<owner/repo>#<n>` or `slack:<channel>:<thread_ts>`, dropped after 7 days.

  The agent only reads it. The main session writes it in the same turn it relays the report:
  - `last_sweep` = the timestamp of the oldest item left over by the 4-item cap, or now when nothing is left over. Rollover items are never lost.
  - `declined` after Zack answers.

  That is the only state.
- **The main session** relays DRAFT and NUDGE lines, and asks PROPOSE items in one AskUserQuestion (multiSelect, up to 4). A yes starts the matching `wait-for`.

### 4. In-the-moment proposals

`/pr` step 4 and board step 8 replace `~/bin/watch add` with one line to Zack: "Watch #n? (a) merge when green and approved (b) just tell me (c) no". On (a) or (b), start `wait-for pr`, adding `--sha` on (a).

## Files

**Add:**
- `bin/wait-for`
- `bin/tests/test_wait_for.py`: the matching cases carried over from `test_watch.py` (config, deploy rule, backfill, rollup), plus new cases for every event line, `CLEAN`/`UNSTABLE`/empty `reviewDecision`, timeout and error, with `gh` stubbed
- `skills/watch/sweep.md`: the agent prompt

**Rewrite:** `skills/watch/SKILL.md` (~100 lines):
- when to propose, and how to start each wait;
- the event table, the merge rule (`--match-head-commit`) and push for urgent events;
- the sweep cron (local-clock note);
- tracking running waits: the main session keeps each background task id and command, and the wrap handoff lists them;
- allow rules and common mistakes.

**Delete:**
- `bin/watch`, `bin/tests/test_watch.py`
- `skills/watch/handle.md`, `kinds.md`, `dispatch-prompts.md`

`bin/tests/__init__.py` stays, for the new test.

**Update:**
- `install.sh` line 46: link `wait-for` instead of `watch`.
- `commands/pr.md` step 4: propose and start `wait-for pr`.
- `skills/board/SKILL.md`:
  - line 29: the gate becomes "when the `### Watches` section exists";
  - line 49: drop the reply-watch-on-sent hook (the sweep covers replies) and the `## Watches` table rebuild;
  - lines 83 and 109: rollover creates the sweep cron, wrap deletes it and lists running waits in the handoff;
  - lines 93-94: propose and start `wait-for pr`.
- `skills/board/page-template.md`: drop the `## Watches` table section.
- `claude-md/CLAUDE.md.template` `### Watches`:
  - keep `Time zone`, `Business hours`, the Slack connector prefix, `Dagster` and `Deploy rules`;
  - drop `Registry`, `Tick interval`, `Quiet hours`, `Requests channel` and the email connector;
  - repoint the Work board `Watch-slack state file` line to the sweep state file.
- `SETUP.md`:
  - rows 19 and 25;
  - a new changelog entry (one dated bullet, newest first, wrapped at ~72 columns, like line 102);
  - lines 179-184.
- `README.md:36`: the registry description.
- Superseded note at the top of both 2026-10-28 docs. This plan goes to `docs/superpowers/plans/2026-10-31-watch-simple.md`.

**Changelog, per-machine steps** (Zack does these by hand, nothing is auto-deleted):
- run `./install.sh`;
- `rm ~/bin/watch`, and archive or delete `~/.claude/watches.json`;
- trim the `### Watches` block;
- delete any `watch tick` cron;
- allow rules become `Bash(~/bin/wait-for *)` plus the Slack read and draft tools, so drop the Gmail and Notion lines.

## PRs

1. Add `bin/wait-for` + tests, `skills/watch/sweep.md`, the new `SKILL.md`, and the `install.sh` link. Nothing old removed yet, so both work side by side.
2. Remove the registry: the script, tests and old docs. Update `/pr`, the board, the template, SETUP, the changelog and the superseded notes.

Per PR: tests first, sonnet implementer in a worktree, opus review, `python3 -m pytest bin/tests/` green.

## Out of scope

- Turning it on on this machine: memory `no-watch-skill` stands until Zack asks.
- Surviving `/clear` mid-wait (accepted: the next sweep re-proposes).
- Email, the requests channel, GitHub auto-merge.
