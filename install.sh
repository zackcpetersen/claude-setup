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
for f in "$REPO_DIR"/bin/query_db "$REPO_DIR"/bin/worktree; do
  chmod +x "$f"
  link "$f" "$HOME/bin/$(basename "$f")"
done

if [[ ! -f "$HOME/.claude/CLAUDE.md" ]]; then
  cp "$REPO_DIR/claude-md/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
  echo "Copied starter CLAUDE.md to ~/.claude/CLAUDE.md - fill in the FILL IN sections."
else
  echo "~/.claude/CLAUDE.md already exists - not touching it. Diff against claude-md/CLAUDE.md manually if you want the generic sections."
fi

echo
echo "Done. Remaining manual steps are listed in SETUP.md."
