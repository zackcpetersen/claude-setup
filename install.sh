#!/usr/bin/env bash
set -euo pipefail

# Installs this repo's Claude Code commands and helper scripts on a new machine.
# Commands and bin scripts are SYMLINKED so edits on any machine are one
# `git commit` away from being backed up. CLAUDE.md is COPIED (never linked)
# because it gets personalized per machine.
#
# Safe to re-run. Existing regular files are backed up to <name>.bak first.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

link() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    rm "$dest"
  elif [[ -e "$dest" ]]; then
    echo "  Backing up existing $dest -> $dest.bak"
    mv "$dest" "$dest.bak"
  fi
  ln -s "$src" "$dest"
  echo "  Linked $dest -> $src"
}

echo "Installing Claude Code commands to ~/.claude/commands ..."
mkdir -p "$HOME/.claude/commands"
for f in "$REPO_DIR"/commands/*.md; do
  link "$f" "$HOME/.claude/commands/$(basename "$f")"
done

echo "Installing Claude Code skills to ~/.claude/skills ..."
mkdir -p "$HOME/.claude/skills"
for d in "$REPO_DIR"/skills/*/; do
  d="${d%/}"
  link "$d" "$HOME/.claude/skills/$(basename "$d")"
done

echo "Installing Claude Code output styles to ~/.claude/output-styles ..."
mkdir -p "$HOME/.claude/output-styles"
for f in "$REPO_DIR"/output-styles/*.md; do
  link "$f" "$HOME/.claude/output-styles/$(basename "$f")"
done

echo "Installing helper scripts to ~/bin ..."
mkdir -p "$HOME/bin"
for f in "$REPO_DIR"/bin/query_db "$REPO_DIR"/bin/worktree "$REPO_DIR"/bin/wait-for "$REPO_DIR"/bin/tidy "$REPO_DIR"/bin/pr-precheck "$REPO_DIR"/bin/eng-stats "$REPO_DIR"/bin/status-feeds; do
  chmod +x "$f"
  link "$f" "$HOME/bin/$(basename "$f")"
done

# Config examples are copied only on a fresh install (no ~/.claude/CLAUDE.md yet). On an
# existing install a missing section can mean the user turned that skill off (deleting
# `### Tidy` turns tidy off), so a copy here would turn it back on at the next update.
fresh=no
[[ -f "$HOME/.claude/CLAUDE.md" ]] || fresh=yes

echo "Per-skill config in ~/.claude/config ..."
mkdir -p "$HOME/.claude/config"
for pair in "board:Work board" "watch:Watches" "tidy:Tidy" "writing-voice:Writing voice"; do
  name="${pair%%:*}"; words="${pair#*:}"
  src="$REPO_DIR/config/$name.example.md"
  dest="$HOME/.claude/config/$name.md"
  if [[ -e "$dest" ]]; then
    continue
  elif [[ "$fresh" == yes ]]; then
    cp "$src" "$dest"
    echo "  Copied $dest - fill in the FILL IN lines"
  elif grep -q "^### $words" "$HOME/.claude/CLAUDE.md" 2>/dev/null; then
    echo "  ### $words is still in ~/.claude/CLAUDE.md - optional: move it to $dest (both places work)"
  else
    echo "  No $dest - copy config/$name.example.md there if you want it"
  fi
done

if [[ ! -f "$HOME/.claude/CLAUDE.md" ]]; then
  cp "$REPO_DIR/claude-md/CLAUDE.md.template" "$HOME/.claude/CLAUDE.md"
  echo "Copied starter CLAUDE.md to ~/.claude/CLAUDE.md - fill in the FILL IN sections."
else
  echo "~/.claude/CLAUDE.md already exists - not touching it. Diff against claude-md/CLAUDE.md.template manually if you want the generic sections."
fi

echo
echo "Done. Remaining manual steps are listed in SETUP.md."
echo "Install the model-discipline plugin (the agent-model-guard hook): see SETUP.md section 4."
