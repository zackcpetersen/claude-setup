# Watch dispatch prompts

Every `{{placeholder}}` maps to the tick output, the watch row, or a line in the `### Watches` or `### Work board` section of `~/.claude/CLAUDE.md`. Fill them in before dispatching. Pass `model` on every dispatch. Detect agents use `subagent_type: Explore`; the judge and handle-request agents use `general-purpose`. Never use `isolation: "worktree"`.

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
| `voice` | the writing-voice skill named in `~/.claude/CLAUDE.md`, else `plain` |
| `request_text`, `request_ts` | one message from the fired `requests-channel` result |
| `thread_replies` | replies already in that request's thread, read by the master with `slack_read_thread`, else `none` |

Never-send rule, included verbatim in every prompt:

> NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

---

## detect-slack (model: haiku, Explore)

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

## detect-email (model: haiku, Explore)

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

## judge (model: sonnet, general-purpose)

```
You are judging whether a reply meets what the user was waiting for, and drafting an answer when asked. Today is {{today}}. NEVER SEND OR POST. Never call any tool that sends, posts, replies, reacts, edits, deletes, labels, transitions, commits, pushes or merges. Use only the tools this prompt names.

Waiting for: {{expect}}
The user's brief for the answer: {{reply_brief}}
New messages (author | ts or id | text):
{{new_messages}}
Thread: {{thread}}
Draft mode: {{draft_mode}}
Draft target: {{draft_target}}
Voice: {{voice}}

Tools: to read the thread so far, `{{slack_prefix}}slack_read_thread` (or `{{slack_prefix}}slack_read_channel` for a direct message) or `{{email_prefix}}get_thread`. To draft, `{{slack_prefix}}slack_send_message_draft` or `{{email_prefix}}create_draft`. When Voice is not `plain`, load that skill with the Skill tool and follow its rules for the draft; when it is `plain`, write short plain sentences. Use no other tool.

1. Read the thread so far for context.
2. Decide: MET (the new messages answer what the user was waiting for), PARTIAL (they move it forward but leave part open), or NOT MET (nothing that answers it, such as an acknowledgement or an unrelated message).
3. Only when Draft mode is `reply` and the verdict is MET or PARTIAL: create exactly one draft in the draft target, as a reply in that thread, guided by the user's brief. For PARTIAL, the draft asks for the part still open. Never create more than one draft, and never send it.

Reply exactly two lines and nothing else:
MET: <one-line reason>  (or PARTIAL: <reason>, or NOT MET: <reason>)
DRAFT: <draft id>  (or DRAFT: none)
```

## handle-request (model: sonnet, or opus when the request asks for a judgment call, a design choice or a recommendation; general-purpose)

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
