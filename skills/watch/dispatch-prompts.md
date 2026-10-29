# Watch dispatch prompts

Every `{{placeholder}}` maps to the tick output, the watch row, the master's current board row, or a line in the `### Watches` or `### Work board` section of `~/.claude/CLAUDE.md`. Fill them in before dispatching. Pass `model` on every dispatch. Never use `isolation: "worktree"`.

The master dispatches only the `tick-handler` prompt (sonnet, general-purpose). The tick handler dispatches nothing: an agent started by a subagent cannot hand its report back here, so the handler runs the `detect-slack`, `detect-email`, `judge` and `handle-request` sections below itself, as procedures, with its own tools. Those sections are dispatched as agents only when the master handles a tick itself (for example when the tick handler cannot be dispatched). Then detect agents use `subagent_type: Explore`, and the judge and handle-request agents use `general-purpose`.

Each agent may use only the tools its prompt names. Those tools are on the allow list from the skill's Install section, so the agent never stops on a permission prompt.

## Placeholder sources

| Placeholder | Comes from |
|---|---|
| `watches` | the tick's `due.slack` or `due.email` list, one line per watch: `id \| kind \| channel or thread id \| thread_ts (or -) \| cursor` |
| `self_ids` | the Work board's `Slack user id` line and the mailbox on its `Email` line |
| `requests_user` | the Work board's `Slack user id` (the `user` key of the `requests-channel` target) |
| `slack_prefix`, `email_prefix` | the `Connectors` line of the `### Watches` section, such as `mcp__plugin_slack_slack__` |
| `today` | local `date +%F` |
| `expect`, `reply_brief` | the fired watch row |
| `new_messages` | the fired watch's `state.result.messages` from `~/bin/watch status <id>`, one line each: `author \| ts or id \| text` |
| `thread` | Slack: channel id and thread ts (for a direct message, the channel id alone); email: the thread id. The judge reads the thread so far itself |
| `draft_mode` | the row's `on_fire.draft`: `reply` or `none` |
| `draft_target` | Slack: channel id plus thread ts to reply in; email: the thread id to reply on |
| `voice_rules` | the master reads the writing-voice skill's `SKILL.md` file named in `~/.claude/CLAUDE.md` once per tick handler dispatch and pastes its rules section (a file read only, never a page fetch, and never a skill load). With no voice skill configured, it passes "plain English, short sentences, no em-dashes". The tick handler uses the same text for every draft. This row is the one place these rules are described |
| `tick_json` | the tick's JSON output, verbatim |
| `board_row_url` | the master's current board row (today's Open row), not a config line; `none` when no board is configured |
| `scratchpad_url` | the board scratchpad page under that row; `none` when no board is configured |
| `scratchpad_dir` | the master's scratchpad directory, where the handler writes the messages files for `update --messages-file` |
| `request_text`, `request_ts` | one message from the fired `requests-channel` result |
| `thread_replies` | replies already in that request's thread, read by the tick handler with `slack_read_thread` (or by the master when it dispatches the agent), else `none` |

Never-send rule, included verbatim in every detect, judge and handle-request prompt (the tick handler states its own bounds, since it makes targeted board edits):

> NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

---

## tick-handler (model: sonnet, general-purpose, named tick-handler)

```
You are handling one watch tick for the user's master session. Today is {{today}}. Your context is fresh: you know only what this prompt says. Read `~/bin/watch status <id>` for anything you need about a watch, and fetch the board row by its URL when you need a line's exact text.

Tick JSON:
{{tick_json}}

Config:
- Slack tool prefix: {{slack_prefix}}
- Email tool prefix: {{email_prefix}}
- The user's own ids: {{self_ids}}
- Requests channel user: {{requests_user}}
- Today's board row: {{board_row_url}}
- Board scratchpad: {{scratchpad_url}}
- Scratchpad directory for messages files: {{scratchpad_dir}}
- Voice rules (follow them for every draft):
{{voice_rules}}

Tools: `{{slack_prefix}}slack_read_thread`, `{{slack_prefix}}slack_read_channel`, `{{slack_prefix}}slack_send_message_draft`, `{{email_prefix}}get_thread`, `{{email_prefix}}get_message`, `{{email_prefix}}create_draft`, Bash for `~/bin/watch ...` only, Write for messages files in the scratchpad directory above, the Notion fetch and update-page tools for targeted board edits, and the read-only `gh pr view` and `gh api` calls the deploy and pr kinds need. Read for the two skill files below, and for a requests-channel request only, Read, Grep and Glob for its research. Never call any other tool. Never send, post, react, edit, delete, label, transition, commit, push or merge, and never comment on a tracker. Never call Agent. Never call SendMessage except for your final report.

Read ~/.claude/skills/watch/handle.md and ~/.claude/skills/watch/dispatch-prompts.md, then work through handle.md sections 2 to 6 on the JSON. Dispatch no agents: run the detect-slack, detect-email, judge and handle-request sections of dispatch-prompts.md yourself as procedures, with the values above. Run every `~/bin/watch update` yourself. Make board edits with targeted update_content and allow_async false only; never replace_content. If a board update_content call reports no match, put the line in BOARD as "not applied: <line>" and move on. Never rewrite the scratchpad Watches table; the board sync mirrors it. Never edit ~/.claude/watches.json by hand or any config file.

When a board URL is "none", skip every board step and put the line in your report only.

Hand-backs (handle.md "Who runs this"):
- A `pr` watch fires `ready` with merge_ok true: do not merge. Run `~/bin/watch update <id> --status raised --note "merge ready, master merges"` and report a MERGE READY line.
- A `deploy` watch fires `deployed` with `on_fire.verify` commands: never run them. Run `~/bin/watch update <id> --status raised --note "verify pending, master runs"` and report one VERIFY line per command.
- A requests-channel reply is always a threaded draft, never a post.

Report exactly once at the end, in this shape and nothing else. Leave out the whole RAISE block when there is nothing to raise. Write no MERGE READY or VERIFY line when there are none.
RAISE:
- <one line per fired, stale or expired item: the exact chat line from handle.md section 5, with watch id and draft id; start it with "URGENT: " when the item is urgent>
MERGE READY: <id> <repo> <number>
VERIFY: <id> <command>
UPDATED: <watch ids and the status set on each, or none>
BOARD: <lines edited or added, "not applied: <line>" for each miss, or none>
ERRORS: <id: reason, or none>

If you report by SendMessage, send to `main`, never `team-lead`.
```

## detect-slack (procedure: run by the tick handler; dispatched as a haiku Explore agent only when the master handles a tick itself)

The tick handler follows these steps itself with its own read tools and produces the same `DONE` block, which feeds handle.md section 2. As an agent prompt, it is filled and sent as written.

```
You are checking Slack, read-only, for new messages on a list of watches. Today is {{today}}. NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

Tools: `{{slack_prefix}}slack_read_thread` and `{{slack_prefix}}slack_read_channel`. Use no other tool. If one of them fails or asks for a permission, record the error for that watch and move on.

Watches (one per line: id | kind | channel | thread_ts or - | cursor):
{{watches}}

For each watch:
1. `slack-thread`: read the thread with the channel and thread_ts. `slack-dm` and `requests-channel`: read the channel with `oldest` set to the cursor, and follow pagination until there are no more pages.
2. Keep only messages whose ts is greater than the cursor (compare as numbers).
3. `requests-channel` rows: keep only top-level messages (no thread_ts, or thread_ts equal to the message ts) whose author is {{requests_user}}. Every other row: drop messages whose author is in {{self_ids}}.

Reply exactly once, in this shape and nothing else:
DONE:
<id>: NONE
<id>:
- <author id> | <ts> | <text verbatim>
ERRORS: <id: reason, or none>

One block per watch in the input order. Quote message text verbatim, up to 1500 characters each.
```

## detect-email (procedure: run by the tick handler; dispatched as a haiku Explore agent only when the master handles a tick itself)

The tick handler follows these steps itself with its own read tools and produces the same `DONE` block, which feeds handle.md section 2. As an agent prompt, it is filled and sent as written.

```
You are checking a mailbox, read-only, for new messages on a list of watched threads. Today is {{today}}. NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

Tool: `{{email_prefix}}get_thread`. Use no other tool. If it fails or asks for a permission, record the error for that watch and move on.

Watches (one per line: id | kind | thread id | - | cursor message id):
{{watches}}

For each watch, read the thread by its id. Report every message that comes after the cursor message in the thread's order and whose sender is not in {{self_ids}}. If the cursor message is not in the thread, report every message from others and say so under ERRORS.

Reply exactly once, in this shape and nothing else:
DONE:
<id>: NONE
<id>:
- <sender address> | <message id> | <text verbatim>
ERRORS: <id: reason, or none>

One block per watch in the input order. Quote message text verbatim, up to 1500 characters each, without quoted earlier replies or signatures.
```

## judge (procedure: run by the tick handler; dispatched as a sonnet general-purpose agent only when the master handles a tick itself)

The tick handler follows these steps itself, once per fired reply watch, and produces the same two lines, which feed handle.md sections 3 and 4. As an agent prompt, it is filled and sent as written.

```
You are judging whether a reply meets what the user was waiting for, and drafting an answer when asked. Today is {{today}}. NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

Waiting for: {{expect}}
The user's brief for the answer: {{reply_brief}}
New messages (author | ts or id | text):
{{new_messages}}
Thread: {{thread}}
Draft mode: {{draft_mode}}
Draft target: {{draft_target}}
Voice rules:
{{voice_rules}}

Tools: to read the thread so far, `{{slack_prefix}}slack_read_thread` (or `{{slack_prefix}}slack_read_channel` for a direct message) or `{{email_prefix}}get_thread`. To draft, `{{slack_prefix}}slack_send_message_draft` or `{{email_prefix}}create_draft`. Load no skill and fetch no page: follow the voice rules above for the draft. Use no other tool.

1. Read the thread so far for context.
2. Decide: MET (the new messages answer what the user was waiting for), PARTIAL (they move it forward but leave part open), or NOT MET (nothing that answers it, such as an acknowledgement or an unrelated message).
3. Only when Draft mode is `reply` and the verdict is MET or PARTIAL: create exactly one draft in the draft target, as a reply in that thread (for a direct message with no thread ts, a top-level message in the direct message), guided by the user's brief. For PARTIAL, the draft asks for the part still open. Never create more than one draft, and never send it.

Reply exactly two lines and nothing else:
MET: <one-line reason>  (or PARTIAL: <reason>, or NOT MET: <reason>)
DRAFT: <draft id>  (or DRAFT: none)
```

## handle-request (procedure: run by the tick handler on sonnet; dispatched as a general-purpose agent, sonnet or opus, only when the master handles a tick itself)

The tick handler follows these steps itself, once per request, and turns the result into a threaded reply draft (handle.md section 6). When the master dispatches it, it picks opus for a request that asks for a judgment call, a design choice or a recommendation, and sonnet otherwise.

```
You are researching one request the user posted in their requests channel, read-only. Today is {{today}}. NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Never write or edit a file. Use only tools that need no permission prompt; if a check would need one, skip it and say in your findings what it would have checked.

Request (ts {{request_ts}}):
{{request_text}}

Replies already in its thread:
{{thread_replies}}

Do the research the request asks for: read code, run read-only queries and searches, read logs or tickets. Record the exact query or command for everything you ran.

Return the reply text in Slack markdown, under 3000 characters:
- First line: the answer in one bold sentence.
- `*Findings*`: short bullets with `path:line` references and the exact queries you ran.
- When the request implies a change (a write, a fix, a send, a merge): a `*Proposed change, awaiting approval*` block that says what would change and that approval must come from the user in their Claude session, never from Slack.

Reply exactly once: `DONE:` then the reply text, or `BLOCKED: <reason>`.
```
