#!/bin/bash
set -euo pipefail

DEST_BRANCH="iterations"
SRC_BRANCH="${1:-main}"

git checkout "$DEST_BRANCH" || { echo "❌ Could not switch to branch '$DEST_BRANCH'"; exit 1; }

if ! git show-ref --verify --quiet "refs/heads/$SRC_BRANCH"; then
  echo "❌ Source branch '$SRC_BRANCH' does not exist."
  exit 1
fi

echo "📥 Pulling snapshot from '$SRC_BRANCH' into '$DEST_BRANCH'..."
git checkout "$SRC_BRANCH" -- .

echo "✅ Snapshot from '$SRC_BRANCH' applied to '$DEST_BRANCH'."
