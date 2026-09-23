#!/usr/bin/env bash
set -euo pipefail

# Brings an already-set-up machine up to date with this repo. Safe to re-run.
#
#   1. git pull --ff-only origin main
#   2. ./install.sh          (relinks everything; idempotent)
#   3. prints what changed since the last run of this script:
#        - commits
#        - SETUP.md changelog entries that need per-machine action
#        - template sections added since then that ~/.claude/CLAUDE.md lacks
#        - leftover .bak files, and plugin cache drift
#   4. records the synced commit in ~/.claude/.claude-setup-synced
#
# The SessionStart nudge hook in SETUP.md section 4 tells you when to run this.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER="$HOME/.claude/.claude-setup-synced"
cd "$REPO_DIR"

before="$(git rev-parse HEAD)"
last="$(cat "$MARKER" 2>/dev/null || true)"
if [[ -z "$last" ]] || ! git cat-file -e "$last^{commit}" 2>/dev/null; then
  last="$before"   # first run, or stale marker: report only what this pull brings
fi

echo "== Pulling origin/main =="
git pull --ff-only origin main
after="$(git rev-parse HEAD)"
echo

echo "== Relinking (install.sh) =="
"$REPO_DIR/install.sh"
echo

echo "== Commits since last sync ($(git rev-parse --short "$last")..$(git rev-parse --short "$after")) =="
if [[ "$last" == "$after" ]]; then
  echo "  none"
else
  git log --oneline "$last..$after" | sed 's/^/  /'
fi
echo

echo "== Changelog entries that need per-machine action (SETUP.md) =="
# Entries look like "- YYYY-MM-DD: ..." and are followed by indented wrap lines.
# Show every entry dated on or after the last synced commit's date.
since="$(git log -1 --format=%cs "$last")"
entries="$(awk -v since="$since" '
  /^### Changelog/            { inlog = 1; next }
  inlog && /^## /             { inlog = 0 }
  inlog && /^- [0-9]{4}-[0-9]{2}-[0-9]{2}:/ { show = (substr($2, 1, 10) >= since) }
  inlog && show && NF         { print "  " $0 }
' SETUP.md)"
if [[ -n "$entries" ]]; then printf '%s\n' "$entries"; else echo "  none"; fi
echo

echo "== Template sections added since last sync that ~/.claude/CLAUDE.md lacks =="
headings_at() {  # headings of the CLAUDE.md template at a given commit (handles the pre-rename path)
  git show "$1:claude-md/CLAUDE.md.template" 2>/dev/null || git show "$1:claude-md/CLAUDE.md" 2>/dev/null || true
}
new_headings="$(comm -13 \
  <(headings_at "$last"  | grep -E '^#{2,3} ' | sort) \
  <(headings_at "$after" | grep -E '^#{2,3} ' | sort))"
missing=""
while IFS= read -r h; do
  [[ -z "$h" ]] && continue
  grep -qxF -- "$h" "$HOME/.claude/CLAUDE.md" 2>/dev/null || missing+="  $h"$'\n'
done <<< "$new_headings"
if [[ -n "$missing" ]]; then
  printf '%s' "$missing"
  echo "  -> copy each from claude-md/CLAUDE.md.template and fill in the FILL INs"
else
  echo "  none"
fi
echo

baks="$(find "$HOME/.claude/commands" "$HOME/.claude/skills" "$HOME/.claude/output-styles" "$HOME/bin" -maxdepth 1 -name '*.bak' 2>/dev/null || true)"
if [[ -n "$baks" ]]; then
  echo "== Leftover .bak files (diff each against the repo file, port anything missing, then delete) =="
  printf '%s\n' "$baks" | sed 's/^/  /'
  echo
fi

cache="$(ls -d "$HOME"/.claude/plugins/cache/claude-setup/model-discipline/*/ 2>/dev/null | head -1 || true)"
if [[ -n "$cache" ]] && ! diff -rq -x .in_use "$cache" "$REPO_DIR/plugins/model-discipline" >/dev/null 2>&1; then
  echo "== model-discipline plugin: installed cache differs from the repo =="
  diff -rq -x .in_use "$cache" "$REPO_DIR/plugins/model-discipline" 2>/dev/null | sed 's/^/  /' || true
  echo "  -> claude plugin marketplace update claude-setup && claude plugin install model-discipline@claude-setup, then restart Claude Code"
  echo
fi

echo "$after" > "$MARKER"
echo "Synced at $(git rev-parse --short "$after"). Recorded in $MARKER."
