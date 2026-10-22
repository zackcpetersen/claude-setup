#!/usr/bin/env bash
# Smoke test for hooks/agent-rules-append. Plain bash, no framework.
#   bash plugins/model-discipline/tests/agent-rules-append.test.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../hooks/agent-rules-append"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the hook passes every dispatch through without it and there is nothing to test."
  exit 0
fi

failures=0
total=0

# check <name> <command...>: one assertion, counted as a case.
check() {
  local name="$1"
  shift
  total=$((total + 1))
  if "$@"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    failures=$((failures + 1))
  fi
}

run() { printf %s "$1" | bash "$HOOK" 2>/dev/null; }

# Output carries the rules block and every original field unchanged.
appended_and_kept() {
  printf %s "$1" | jq -e '
    .hookSpecificOutput.permissionDecision == "allow"
    and (.hookSpecificOutput.updatedInput.prompt | startswith("do the thing"))
    and (.hookSpecificOutput.updatedInput.prompt | contains("## Sub-agent rules"))
    and .hookSpecificOutput.updatedInput.subagent_type == "general-purpose"
    and .hookSpecificOutput.updatedInput.model == "sonnet"
    and .hookSpecificOutput.updatedInput.description == "Fix a bug"
    and .hookSpecificOutput.updatedInput.run_in_background == true
    and .hookSpecificOutput.updatedInput.name == "fixer"
  ' >/dev/null 2>&1
}
empty() { [[ -z "$1" ]]; }

out="$(run '{"tool_input":{"subagent_type":"general-purpose","model":"sonnet","description":"Fix a bug","prompt":"do the thing","run_in_background":true,"name":"fixer"}}')"
check "general-purpose prompt gets the block and keeps every other field" appended_and_kept "$out"

out="$(run '{"tool_input":{"model":"sonnet","description":"x","prompt":"do the thing"}}')"
check "untyped dispatch gets the block" \
  bash -c 'printf %s "$1" | jq -e ".hookSpecificOutput.updatedInput.prompt | contains(\"## Sub-agent rules\")" >/dev/null' _ "$out"

out="$(run '{"tool_input":{"subagent_type":"Explore","model":"sonnet","prompt":"look around"}}')"
check "Explore is untouched" empty "$out"

out="$(run '{"tool_input":{"subagent_type":"general-purpose","model":"sonnet","prompt":"work\n\n## Sub-agent rules\nalready here"}}')"
check "prompt with the marker is untouched" empty "$out"

out="$(run '{"tool_input":{"subagent_type":"fork","prompt":"carry on"}}')"
check "fork is untouched" empty "$out"

out="$(printf %s 'not json {' | bash "$HOOK" 2>/dev/null)"
code=$?
check "bad JSON exits 0 with no output" test "$code" -eq 0 -a -z "$out"

echo
if [[ "$failures" -eq 0 ]]; then
  echo "$total/$total passed."
  exit 0
fi
echo "$failures failed."
exit 1
