#!/bin/bash
set -euo pipefail

BRANCH="iterations"

git checkout "$BRANCH"
if ! git diff-index --quiet HEAD --; then
  echo "❌ Uncommitted changes in '$BRANCH'. Please commit or stash them before cleaning."
  exit 1
fi

timestamp=$(date +%Y%m%d-%H%M)
backup_branch="$BRANCH-backup-$timestamp"
git branch "$backup_branch"
echo "🛡️ Backup created as '$backup_branch'"

echo "📉 Starting interactive root rebase of '$BRANCH'..."
git rebase -i --root || {
  echo "❌ Rebase failed. You can restore from '$backup_branch'."
  exit 1
}

echo "✅ '$BRANCH' cleaned. Backup: $backup_branch"
