#!/usr/bin/env bash
# Repository settings that only an administrator can apply. Run once, as the owner:
#   bash scripts/apply-repo-settings.sh leosoftlima/eduFidelity
# Requires the GitHub CLI (gh) logged in with admin rights on the repository.
set -euo pipefail
repo="${1:?usage: apply-repo-settings.sh OWNER/REPO}"

# Merge methods (CONTRIBUTING §2): squash for single pull requests, merge commits for
# stacks, no rebase merging; delete branches after merge; titles become commit messages.
gh api -X PATCH "repos/$repo" \
  -F allow_squash_merge=true -F allow_merge_commit=true -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true -F allow_update_branch=true \
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY \
  -F has_wiki=false >/dev/null

# Vulnerability alerts, automated security fixes and private vulnerability reporting.
gh api -X PUT "repos/$repo/vulnerability-alerts" >/dev/null
gh api -X PUT "repos/$repo/automated-security-fixes" >/dev/null
gh api -X PUT "repos/$repo/private-vulnerability-reporting" >/dev/null

# Trunk protection (pull request, code owner review, CI green, no force push or deletion).
existing=$(gh api "repos/$repo/rulesets" --jq '.[] | select(.name=="trunk protection") | .id')
if [ -n "$existing" ]; then
  gh api -X PUT "repos/$repo/rulesets/$existing" --input .github/rulesets/default-branch.json >/dev/null
else
  gh api -X POST "repos/$repo/rulesets" --input .github/rulesets/default-branch.json >/dev/null
fi

# Labels used by the issue templates.
for label in "bug:d73a4a" "enhancement:a2eeef" "method:5319e7"; do
  gh label create "${label%%:*}" --color "${label##*:}" --repo "$repo" --force >/dev/null
done
echo "settings applied to $repo"
