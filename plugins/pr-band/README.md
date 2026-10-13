# pr-band

A Claude Code mod that shows your open pull requests in the band above the prompt, labeled by ticket key, with CI and review status. It is part of the [claude-setup](https://github.com/zackcpetersen/claude-setup) repo and installs through that repo's plugin marketplace.

## What it shows

One row, at most 6 PRs, cut to fit the width of the band:

```
PRs  ✓ DE-3240  ✗ DE-3132  ● DE-2733 (review)  ✓✓ DE-3106
```

- `✓` checks passed, `✗` checks failed, `●` checks pending or none reported.
- A second `✓` means the PR is approved. `(review)` means changes were requested.
- The label is the `[ABC-123]` ticket key from the PR title, or `#<number>` when the title has none.
- Draft PRs are dimmed.
- If `gh` fails (not installed, not logged in, bad output), the row reads `PRs: gh unavailable` in dim text.
- With no open PRs, it draws nothing.

The list comes from `gh api graphql`, searching `is:pr is:open author:@me org:<org>`, so `gh` must be installed and logged in.

## Install

```
/plugin marketplace add zackcpetersen/claude-setup
/plugin install pr-band@claude-setup
/reload-plugins
```

Mods need Claude Code 2.1.287 or newer. Tested with 2.1.296.

## Configuration

Set these in `/config` or when `/plugin` asks:

- `org` - the GitHub org to search. Default `reserv-technologies`.
- `refreshSeconds` - how often to ask GitHub, in seconds. Default `120`, minimum `30`.

## Where it draws

- Draws in the terminal and in the Desktop app's Code tab.
- Does not draw in the VS Code chat panel or on claude.ai/code.

## Cost

One GraphQL call when the session starts, then one every `refreshSeconds` per open session. At the default that is 30 calls an hour per session, far under GitHub's GraphQL rate limit.

## Verify it is running

- `claude plugin validate plugins/pr-band` lists `session.start` and `ui.render{component=AbovePrompt}` hooks and the `$.process.run` call.
- `claude plugin test plugins/pr-band` passes.
- The band shows your PRs, and still shows them after `/clear`.

## Troubleshooting

- `PRs: gh unavailable` in the Desktop app launched from the Dock usually means `gh` is not on its `PATH` (Homebrew puts it in `/opt/homebrew/bin`).
- Nothing drawn at all: run `claude --debug-file ./mod-debug.log` and look for `pr-band` lines.

## Iterating locally

Installed plugins are cached by `version`, so edits to the repo do not reach an installed copy until you bump `version` and reinstall. While developing, run `claude --plugin-dir ~/Projects/claude-setup/plugins/pr-band`, which reloads the mod on save.
