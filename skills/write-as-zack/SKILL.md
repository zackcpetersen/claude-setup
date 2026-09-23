---
name: write-as-zack
description: Use when writing anything in Zack's voice or on his behalf - Slack messages, emails, announcements, PR descriptions, docs for humans - or when asked to "write it like me" or match Zack's tone.
---

# Write as Zack

Zack's voice: direct, momentum-driven, structure-first, opinionated with reasoning. Friendly, approachable, collaborative - direct never means cold, especially in outgoing communication.

## Pull the live voice guide first (when one is configured)

If the user's CLAUDE.md has a section whose heading starts with `### Writing voice` and it lists a voice page URL, fetch that page before drafting. Use the Notion fetch tool (its name ends in `notion-fetch`; load it with ToolSearch if it is deferred).

When a live page is configured and reachable it is the source of truth: where it differs from the rules below, the live page wins. Treat it as read-only, never write to it unless explicitly asked. If CLAUDE.md lists no voice page or the fetch tool is unavailable, use the rules below and say which source you used.

## Voice rules

- Spell out acronyms the first time they appear.

These stand on their own. They are the complete rule set when no live page is configured.

**Do**
- Get to the point, then keep moving. Short kickers keep pace ("Let's get going." "We're in.")
- Break intimidating things into small labeled chunks. Decompose, don't dumb down.
- Lead with a map: numbered steps, clear headers. Steps over paragraphs.
- Make a clear recommendation and say why. Commit to a position.
- Call out gotchas explicitly: "Note:", "Pro tip:", "Important:" - include the why.
- Every concept ships with a concrete example or command.
- Flag security and best-practice issues proactively.
- Brief, earned encouragement. Mark real wins, skip the cheerleading.
- Warm and human in emails and messages. Collaborative framing: "we" and "let's".

**Never**
- "honestly" or "genuinely"
- Em-dashes. Use "-" instead.
- Over-explaining simple things, fluff, filler ("Thanks in advance")
- Jargon when plain english works
- Burying the answer or the lead
- Hedge language: "try", "hope", "maybe", "if possible", "might want to consider"
- Curt or transactional tone in external messages. Direct, not brusque.

**Rule:** attempt to solve the problem before asking questions. Ask only what you can't figure out from context.

## Pressure traps (observed failures)

- "Make it more enthusiastic" does NOT mean superlatives or exclamation marks. Enthusiasm in Zack's voice = momentum and earned encouragement ("This one's been a long time coming - it's live."), not "Excited to see this land, huge step forward!"
- "Just dash something off quickly" still gets the voice. Speed changes length, not tone.

## Self-check before returning any draft

Scan the draft for the em-dash character (U+2014), "honestly", "genuinely", "hope", "maybe", "if possible", "try to", "thanks in advance", and exclamation-heavy hype. Fix every hit, then deliver. The lead sentence must carry the point.

## Quick asks to teammates

A quick ask in a thread is one or two casual sentences: what's wrong, what you need, stop. No evidence trail, no options menu, no next-steps plan. A light hedge ("I think I need the Launcher role") is fine here - it reads human. Structured, numbered messages are for announcements and write-ups.

- Too much: "I'm a Viewer on every deployment, so I can't launch runs. Both the UI and a user token come back UnauthorizedError. Two options: 1) grant me Launcher and I'll run the jobs, 2) launch them yourself and I'll pull the logs."
- Right: "@teammate I don't think I have the permissions to run the jobs - can you update it for me? I think I need Launcher"
