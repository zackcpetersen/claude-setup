#!/usr/bin/env bash
# Smoke test for hooks/review-target-guard. Plain bash, no framework.
#   bash plugins/model-discipline/tests/review-target-guard.test.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../hooks/review-target-guard"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the hook passes every call through without it."
  exit 0
fi

failures=0
total=0
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
denied() { printf %s "$1" | jq -e '.hookSpecificOutput.permissionDecision == "deny" and (.hookSpecificOutput.permissionDecisionReason | contains("full PR URL"))' >/dev/null 2>&1; }
empty() { [[ -z "$1" ]]; }

check "Skill call with a bare number is denied" denied "$(run '{"tool_name":"Skill","tool_input":{"skill":"code-review","args":"medium 123"}}')"
check "Skill call with #123 is denied" denied "$(run '{"tool_name":"Skill","tool_input":{"skill":"code-review","args":"#123"}}')"
check "Skill call with the full URL is allowed" empty "$(run '{"tool_name":"Skill","tool_input":{"skill":"code-review","args":"medium https://github.com/acme/app/pull/123"}}')"
check "other skills are allowed" empty "$(run '{"tool_name":"Skill","tool_input":{"skill":"tidy","args":"medium 123"}}')"
check "Agent prompt with a bare number is denied" denied "$(run '{"tool_name":"Agent","tool_input":{"prompt":"Run /code-review high 42 and report."}}')"
check "Agent prompt with placeholder text is allowed" empty "$(run '{"tool_name":"Agent","tool_input":{"prompt":"Run /code-review <effort> <PR URL> and report."}}')"
check "Agent prompt quoting a bare-number example in backticks is allowed" empty "$(run '{"tool_name":"Agent","tool_input":{"prompt":"Never write `/code-review 2249` with a bare number; pass the URL."}}')"
check "Agent prompt with the full URL is allowed" empty "$(run '{"tool_name":"Agent","tool_input":{"prompt":"Run /code-review medium https://github.com/acme/app/pull/7"}}')"

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
