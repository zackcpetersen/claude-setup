#!/usr/bin/env bash
# Smoke test for hooks/context-warn. Plain bash, no framework.
#   bash plugins/model-discipline/tests/context-warn.test.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../hooks/context-warn"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the hook does nothing without it."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
mkdir -p "$HOME"
unset CLAUDE_CONTEXT_WARN_AT
T="$TMP/transcript.jsonl"

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

# transcript <tokens>: a user line, a sidechain entry that must be ignored, then a main entry.
transcript() {
  {
    echo '{"type":"user","message":{"content":"hi"}}'
    echo '{"type":"assistant","isSidechain":true,"message":{"usage":{"input_tokens":999999}}}'
    printf '{"type":"assistant","isSidechain":false,"message":{"usage":{"input_tokens":%d,"cache_read_input_tokens":%d,"cache_creation_input_tokens":1000}}}\n' 1000 "$(( $1 - 2000 ))"
    echo '{"type":"system","subtype":"x"}'
  } > "$T"
}
input() { printf '{"session_id":"s1","transcript_path":"%s"%s}' "$T" "${1:-}"; }
run() { input "${1:-}" | bash "$HOOK" 2>/dev/null; }
empty() { [[ -z "$1" ]]; }
warns() { printf %s "$1" | jq -e '.hookSpecificOutput.hookEventName == "PostToolUse" and (.hookSpecificOutput.additionalContext | contains("Context is at 160k tokens (warning line 150k)"))' >/dev/null 2>&1; }

transcript 100000
check "below the line: no output" empty "$(run)"

transcript 160000
check "above the line: one warning" warns "$(run)"
check "second call above: no output" empty "$(run)"

transcript 50000
out="$(run)"
check "back below: no output and marker removed" bash -c '[[ -z "$1" && ! -e "$2" ]]' _ "$out" "$HOME/.claude/context-warn/s1"
transcript 160000
check "next crossing warns again" warns "$(run)"

rm -rf "$HOME/.claude/context-warn"
check "agent_id set: no output" empty "$(run ',"agent_id":"a123"')"

check "CLAUDE_CONTEXT_WARN_AT=off: no output" empty "$(input | CLAUDE_CONTEXT_WARN_AT=off bash "$HOOK" 2>/dev/null)"

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
