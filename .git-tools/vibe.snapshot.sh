#!/bin/bash
set -euo pipefail

ITER_BRANCH="iterations"
MAIN_BRANCH="main"

# 1. Ensure we're on the correct branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [[ "$CURRENT_BRANCH" != "$ITER_BRANCH" ]]; then
  echo "🚫 You must be on the '$ITER_BRANCH' branch to run 'git vibe.push'."
  echo "💡 Run: git checkout $ITER_BRANCH"
  exit 1
fi

# 2. Ensure everything is committed
if ! git diff-index --quiet HEAD --; then
  echo "🚫 Uncommitted changes in '$ITER_BRANCH'. Please commit or stash them first."
  exit 1
fi

# 3. Generate commit message
ITER_HASH=$(git rev-parse --short HEAD)
USER_MSG=${1:-"Snapshot from $ITER_BRANCH"}
COMMIT_MSG="${ITER_HASH} - ${USER_MSG}"

# 4. Ensure MAIN_BRANCH exists
if ! git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
  echo "🚫 Target branch '$MAIN_BRANCH' does not exist."
  exit 1
fi

# 5. Switch to main safely
echo "📦 Applying snapshot from '$ITER_BRANCH' to '$MAIN_BRANCH'..."
git checkout "$MAIN_BRANCH" || {
  echo "❌ Failed to checkout '$MAIN_BRANCH'."
  exit 1
}

# 6. Apply working tree
git checkout "$ITER_BRANCH" -- .

# 7. Commit snapshot
git commit -am "$COMMIT_MSG"

# 8. Return to original branch
git checkout "$ITER_BRANCH"

echo "✅ Snapshot pushed to '$MAIN_BRANCH':"
echo "   $COMMIT_MSG"
