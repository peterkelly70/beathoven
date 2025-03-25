#!/bin/bash
set -euo pipefail

ITER_BRANCH="iterations"
MAIN_BRANCH="main"

# Ensure we're on the iteration branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "$ITER_BRANCH" ]]; then
  echo "🚫 You must be on the '$ITER_BRANCH' branch to run vibe.push."
  exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
  echo "🚫 Uncommitted changes in '$ITER_BRANCH'. Please commit or stash them first."
  exit 1
fi

# Get commit info
HASH=$(git rev-parse --short HEAD)
MSG="${1:-Snapshot from $ITER_BRANCH}"
COMMIT_MSG="$HASH - $MSG"

# Switch to main and apply snapshot
echo "📦 Applying snapshot from '$ITER_BRANCH' to '$MAIN_BRANCH'..."
git checkout "$MAIN_BRANCH" || { echo "❌ Failed to checkout '$MAIN_BRANCH'"; exit 1; }
git checkout "$ITER_BRANCH" -- .

git commit -am "$COMMIT_MSG"
git checkout "$ITER_BRANCH"

echo "✅ Snapshot pushed to '$MAIN_BRANCH': $COMMIT_MSG"
