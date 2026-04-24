#!/bin/bash

# Sync ai-frame project to git repo and commit changes

if [ -z "$1" ]; then
    echo "Usage: $0 <commit message>"
    exit 1
fi

SOURCE_DIR="/Users/chee/zapier ai project/coding/ai-frame"
GIT_REPO="/Volumes/apps/git/ai-frame"

# Sync files from source to git repo (excluding .git and user data)
rsync -av --delete \
    --exclude '.git' \
    --exclude 'users/*/conversations/' \
    --exclude 'users/*/notifications.json' \
    --exclude 'logs/*.log' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$SOURCE_DIR/" "$GIT_REPO/"

# Change to git repo
cd "$GIT_REPO" || exit 1

# Add all changes
git add -A

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "No changes to commit"
    exit 0
fi

# Commit with the provided message
git commit -m "$1"

echo "Changes committed to $GIT_REPO"
