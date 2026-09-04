#!/usr/bin/env bash
# SessionStart hook: re-root a still-empty auto-created branch onto `develop`.
#
# GitHub's default branch for a repo is usually `main`, so tooling that creates
# a working branch automatically (Claude Code on the web, Cursor background
# agents) may start from `main` — missing everything that has landed on
# `develop` since the last release. This fixes that silently, but ONLY when the
# branch has no commits of its own, so it can never discard work.
set -euo pipefail

git rev-parse --git-dir >/dev/null 2>&1 || exit 0
git fetch origin develop --quiet 2>/dev/null || exit 0

branch="$(git rev-parse --abbrev-ref HEAD)"
case "$branch" in
  main|develop|HEAD) exit 0 ;;
esac

# Already based on develop? Nothing to do.
if git merge-base --is-ancestor origin/develop HEAD 2>/dev/null; then
  exit 0
fi

# Any commits of our own? Then re-rooting would rewrite them — warn instead.
if [ "$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)" -gt 0 ]; then
  echo "WARNING: '$branch' is not based on develop and already has commits."
  echo "Run: git merge origin/develop"
  exit 0
fi

# Empty branch: re-root for free (preserves uncommitted working-tree changes).
git checkout -B "$branch" origin/develop --quiet
echo "Re-rooted '$branch' onto origin/develop."
