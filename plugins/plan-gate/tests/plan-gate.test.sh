#!/usr/bin/env bash
# Smoke test for hooks/plan-gate. Plain bash, no framework.
#   bash plugins/plan-gate/tests/plan-gate.test.sh
#
# Every case runs with a throwaway HOME so the real ~/.claude/plan-reviews
# on the machine running the test is never read or consumed.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/../hooks/plan-gate"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq is not installed; the gate denies every plan without it and there is nothing to test."
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
reviews="$tmp/home/.claude/plan-reviews"
mkdir -p "$reviews"

# Same key /self-review writes: first 16 hex chars of sha256 of the directory.
key() { printf %s "$1" | shasum -a 256 | cut -c1-16; }

failures=0
total=0

# run <name> <expected: deny|allow> <payload json>
run() {
  local name="$1" expected="$2" payload="$3" out actual
  total=$((total + 1))
  out="$(printf %s "$payload" | HOME="$tmp/home" bash "$GATE" 2>/dev/null)"
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

# check <name> <command...>: an extra assertion counted like a case.
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

proj="/tmp/plan-gate-test/project"
other="/tmp/plan-gate-test/other"

run "no marker is denied" deny \
  "{\"cwd\":\"$proj\"}"

touch "$reviews/$(key "$proj")"
run "fresh marker is allowed" allow \
  "{\"cwd\":\"$proj\"}"
check "fresh marker is consumed" test ! -e "$reviews/$(key "$proj")"

touch -t "$(date -v-3H +%Y%m%d%H%M 2>/dev/null || date -d '3 hours ago' +%Y%m%d%H%M)" "$reviews/$(key "$proj")"
run "marker older than two hours is denied" deny \
  "{\"cwd\":\"$proj\"}"

touch "$reviews/$(key "")"
run "empty cwd is denied" deny \
  "{\"cwd\":\"\"}"

touch "$reviews/$(key "$other")"
run "marker for a different project is denied" deny \
  "{\"cwd\":\"$proj\"}"

echo
if [[ "$failures" -eq 0 ]]; then
  echo "$total/$total passed."
  exit 0
fi
echo "$failures failed."
exit 1
