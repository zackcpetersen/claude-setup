#!/usr/bin/env bash
# Smoke test for hooks/agent-model-guard. Plain bash, no framework.
#   bash plugins/model-discipline/tests/agent-model-guard.test.sh
#
# Every case runs with a throwaway CLAUDE_PROJECT_DIR and HOME so the agent
# definitions on the machine running the test can never change the result.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/../hooks/agent-model-guard"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the guard fails open without it and there is nothing to test."
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/proj/.claude/agents" "$tmp/home/.claude/agents"

# Transcript fixtures: one assistant entry naming the session model.
printf '%s\n' '{"type":"assistant","message":{"model":"claude-fable-5-1"}}' > "$tmp/fable.jsonl"
printf '%s\n' '{"type":"assistant","message":{"model":"claude-opus-5"}}' > "$tmp/opus.jsonl"

# A project agent whose definition pins a model.
cat > "$tmp/proj/.claude/agents/pinned-agent.md" <<'MD'
---
name: pinned-agent
description: Test fixture with a model pin.
model: sonnet
---
Body.
MD

failures=0

# run <name> <expected: deny|allow> <payload json>
run() {
  local name="$1" expected="$2" payload="$3" out actual
  out="$(printf %s "$payload" \
    | CLAUDE_PROJECT_DIR="$tmp/proj" HOME="$tmp/home" bash "$GUARD" 2>/dev/null)"
  if printf %s "$out" | grep -q '"permissionDecision":"deny"'; then
    actual="deny"
  else
    actual="allow"
  fi
  if [[ "$actual" == "$expected" ]]; then
    echo "PASS: $name (expected $expected)"
  else
    echo "FAIL: $name (expected $expected, got $actual)"
    failures=$((failures + 1))
  fi
}

run "no model on an expensive session is denied" deny \
  "{\"tool_input\":{\"subagent_type\":\"general-purpose\"},\"transcript_path\":\"$tmp/fable.jsonl\"}"

run "explicit model is allowed" allow \
  "{\"tool_input\":{\"subagent_type\":\"general-purpose\",\"model\":\"sonnet\"},\"transcript_path\":\"$tmp/fable.jsonl\"}"

run "fork is allowed without a model" allow \
  "{\"tool_input\":{\"subagent_type\":\"fork\"},\"transcript_path\":\"$tmp/fable.jsonl\"}"

run "no model on a cheaper session is allowed" allow \
  "{\"tool_input\":{\"subagent_type\":\"general-purpose\"},\"transcript_path\":\"$tmp/opus.jsonl\"}"

run "pinned agent is allowed without a model" allow \
  "{\"tool_input\":{\"subagent_type\":\"pinned-agent\"},\"transcript_path\":\"$tmp/fable.jsonl\"}"

echo
if [[ "$failures" -eq 0 ]]; then
  echo "5/5 passed."
  exit 0
fi
echo "$failures failed."
exit 1
