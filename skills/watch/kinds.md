# Watch kinds

What each kind checks, its defaults, and the keys its spec needs. `~/bin/watch add` fills every default you leave out, so a spec only names what differs.

## Kinds

| Kind | Check | Default cadence (`every`, then `slow_every`) | Expiry rule | On fire, by default |
|---|---|---|---|---|
| `slack-thread` | the tick handler reads the thread since the cursor (detect-slack procedure) | 10m, then 60m | `reply` | judge the reply, draft an answer, raise with the draft |
| `slack-dm` | the tick handler reads the direct message channel since the cursor | 10m, then 60m | `reply` | same as `slack-thread` |
| `email-thread` | the tick handler reads the mailbox thread after the cursor message (detect-email procedure) | 20m, then 60m | `reply` | same as `slack-thread` |
| `pr` | script: `gh pr view` state, merge state, review decision, check rollup | 15m | `until-closed` | raise failed checks or changes requested; the master merges when pre-approved, green and approved; otherwise raise "ready to merge?" |
| `deploy` | script: the repo's deploy rule from the `Deploy rules` config | 30m | `two-days` | the master runs the `verify` commands and raises the result; urgent when verification fails |
| `dagster-run` | script: Dagster GraphQL run status | 5m | `until-terminal` | raise the outcome; failure is urgent |
| `dagster-backfill` | script: Dagster GraphQL backfill status, finished only when every partition is terminal | 5m | `until-terminal` | same as `dagster-run` |
| `requests-channel` | the tick handler reads the configured channel for new top-level posts by the configured user | 10m | `never` | research each request and draft a reply in its thread (handle.md section 6) |

Quiet hours (the `Quiet hours` config line, weekends included unless it says `weekends: poll`) pause every watch with `quiet: true`. Dagster kinds default to `quiet: false`. Set `quiet: false` on any other watch the user wants checked "through the night".

## Expiry rules

The `expires` field takes one of these names, or an absolute ISO 8601 time with a UTC offset (hard expiry at that moment).

| Rule | Soft (raise once, keep watching) | Hard (watch ends `expired`) |
|---|---|---|
| `reply` | 1 business day after creation: raise "no reply yet on <thread>, nudge?" and slow to `slow_every` | 5 business days after creation |
| `until-closed` | none | none; the watch ends when the PR merges or closes |
| `two-days` | none | 48 hours after creation |
| `until-terminal` | when the run passes the target's `expected_hours` | none; the watch ends when the run is terminal |
| `never` | none | none |

Business days use the `Business hours` config line and the `Time zone` line, Monday to Friday.

## Spec fields

`~/bin/watch add --file <path>` reads one JSON object with these keys (only `kind` and `target` are required):

| Key | Meaning |
|---|---|
| `kind` | one of the kinds above |
| `target` | kind-specific keys, below |
| `expect` | one sentence: what counts as the event |
| `reply_brief` | reply watches only: what the user wants the answer draft to say, in their words |
| `every`, `slow_every` | durations like `10m` or `2h` |
| `after` | earliest check time, ISO 8601 with an offset |
| `expires` | a rule name above, or an ISO 8601 time with an offset |
| `quiet` | `true` respects quiet hours, `false` polls through them |
| `urgent` | `true` adds a push notification to every raise |
| `on_fire` | `verify` (list of read-only shell commands), `draft` (`reply` or `none`), `then` (a follow-up watch spec); never `merge`, which only `update --merge` sets |
| `cursor` | the starting point, below |
| `created_by` | `chat`, `board`, `pr`, `rollover` or `script` |
| `board_line` | the exact text of the board line this watch belongs to, when there is one |

`add` is idempotent: a spec whose kind and target match an open watch prints that watch's id and changes nothing.

## Targets and starting cursors

| Kind | Target keys | Starting cursor |
|---|---|---|
| `slack-thread` | `channel`, `thread_ts` | the add time, unless the spec gives a Slack ts (the board hook passes the sent message's ts) |
| `slack-dm` | `channel` | the add time, unless the spec gives a Slack ts |
| `email-thread` | `thread_id` | required: the id of the newest message in the thread at add time |
| `pr` | `repo` (`owner/name`), `number` | none; the first check sets it |
| `deploy` | `repo`, `sha` | none; the first check sets it |
| `dagster-run` | `run_id`, optional `expected_hours` | none |
| `dagster-backfill` | `backfill_id`, optional `expected_hours` | none |
| `requests-channel` | `channel`, `user` | the requests state file (the Work board's watch-slack state file line), else the add time |

Messages from the user's own Slack id or mailbox never fire a watch, except on the `requests-channel` watch, which fires only on them.

## Deploy rules

One line per repo under `Deploy rules` in the `### Watches` config. The script compares the watched sha with a ref through the GitHub compare API; "contains" means the compare status is `identical` or `ahead`.

| Rule | Deployed when | Fingerprint (the cursor) | Result keys |
|---|---|---|---|
| `workflow <name> on <branch>` | the newest of the last five completed runs of that workflow on that branch whose head contains the sha succeeded; a failed or timed-out run fires `deploy_failed`; cancelled and skipped runs are passed over | the run id | `run_id` |
| `release-tag` | the latest release tag contains the sha | the tag name | `tag` |
| `branch <name>` | the branch head contains the sha | the branch head sha | none |

## Events

Script kinds fire with an `event` and a `result`. A watch fires again only when its fingerprint changes, so the same state never raises twice.

| Kind | Event | Result keys | Urgent |
|---|---|---|---|
| `pr` | `merged` (only once the merge commit exists) | `merge_sha` | no |
| `pr` | `closed` | none | no |
| `pr` | `checks_failed` | `urgent` | yes |
| `pr` | `changes_requested` | none | no |
| `pr` | `head_moved` (the head sha changed since the merge approval) | none | no |
| `pr` | `ready` (checks green and review approved) | `merge_ok` (`true` when a merge approval exists for this head) | no |
| `deploy` | `deployed` | `run_id` or `tag` | no |
| `deploy` | `deploy_failed` | `run_id`, `urgent` | yes |
| `dagster-run`, `dagster-backfill` | `succeeded` | `run_id` or `backfill_id`, `status` | no |
| `dagster-run`, `dagster-backfill` | `failed` (failed or canceled) | `run_id` or `backfill_id`, `status`, `urgent` | yes |

Agent kinds (`slack-thread`, `slack-dm`, `email-thread`, `requests-channel`) fire when `update --messages-file` records new messages; their result is `{"messages": [...]}`.

## Follow-up watches (`then`)

`on_fire.then` holds a partial spec registered by `~/bin/watch add --then-of <id>` after the watch fires. Any string may use `{name}` placeholders for keys of the fired watch's result, such as `{merge_sha}`, `{run_id}` or `{tag}`; a value that is one whole placeholder keeps its type. The follow-up inherits `created_by`. An unfilled placeholder fails the add with exit 2 and names it.

Example, "verify once it deploys" on a PR watch:

```json
{"kind": "pr", "target": {"repo": "owner/app", "number": 123},
 "expect": "merged",
 "on_fire": {"then": {"kind": "deploy", "target": {"repo": "owner/app", "sha": "{merge_sha}"},
                      "expect": "the change is live",
                      "on_fire": {"verify": ["<read-only command the user named>"]}}}}
```
