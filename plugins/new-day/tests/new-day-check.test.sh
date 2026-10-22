#!/usr/bin/env bash
# Smoke test for hooks/new-day-check. Plain bash, no framework.
#   bash plugins/new-day/tests/new-day-check.test.sh
#
# Every case runs with a throwaway HOME so the real
# ~/.claude/daily-auth-last-run.json on the machine running the test is
# never read.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../hooks/new-day-check"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the hook stays silent without it and there is nothing to test."
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home/.claude"
results="$tmp/home/.claude/daily-auth-last-run.json"

today="$(date +%F)"
yesterday="$(date -v-1d +%F 2>/dev/null || date -d yesterday +%F)"

failures=0
total=0

# run <name> <expected: nudge|silent> <stdin>
run() {
  local name="$1" expected="$2" payload="$3" out code actual
  total=$((total + 1))
  out="$(printf %s "$payload" | HOME="$tmp/home" bash "$HOOK" 2>/dev/null)"
  code=$?
  if [[ "$code" -ne 0 ]]; then
    actual="exit $code"
  elif [[ -z "$out" ]]; then
    actual="silent"
  elif printf %s "$out" | jq -e '.hookSpecificOutput.additionalContext | contains("daily-auth has not run yet")' >/dev/null 2>&1; then
    actual="nudge"
  else
    actual="unexpected output"
  fi
  if [[ "$actual" == "$expected" ]]; then
    echo "PASS: $name (expected $expected)"
  else
    echo "FAIL: $name (expected $expected, got $actual)"
    failures=$((failures + 1))
  fi
}

human='{"prompt":"what is next today?"}'

printf '{"date":"%s","at":"08:00Z","results":[]}\n' "$yesterday" > "$results"
run "stale results file nudges" nudge "$human"
run "stale results file nudges again on the next prompt" nudge "$human"

run "task notification is silent" silent \
  '{"prompt":"<task-notification>\n<task-id>abc</task-id>\n<summary>done</summary>\n</task-notification>"}'
run "message from another session is silent" silent \
  '{"prompt":"Another Claude session sent a message: <teammate-message teammate_id=\"x\">hi</teammate-message>"}'
run "subagent hand-back is silent" silent \
  '{"prompt":"<agent-message from=\"worker\">[Subagent hand-back] done</agent-message>"}'
run "loop tick is silent" silent \
  '{"prompt":"<<autonomous-loop>>"}'

rm -f "$results"
run "missing results file nudges" nudge "$human"

printf '{"date":"%s","at":"08:00Z","results":[]}\n' "$today" > "$results"
run "today's results file is silent" silent "$human"

rm -f "$results"
run "bad JSON on stdin exits 0 silently" silent 'not json {'

echo
if [[ "$failures" -eq 0 ]]; then
  echo "$total/$total passed."
  exit 0
fi
echo "$failures failed."
exit 1
