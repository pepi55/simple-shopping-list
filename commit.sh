#!/usr/bin/env bash
set -e
# Stage all changes (including deletions and new files)
# This script assumes you are in the repository root.

git add -A
# Commit with a conventional commit message summarizing the changes
# - chore(deps): update requirements, remove obsolete lockfile, add documentation files

git commit -m "chore(deps): update requirements, remove obsolete lockfile, add docs"
# Self-delete after successful commit
rm -- "$0"
