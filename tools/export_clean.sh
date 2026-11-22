#!/usr/bin/env bash
# Export the current tree as ONE commit with no history, ready to push to a fresh repository.
# The old history (and GitHub's pull-request refs) stays in the old, private repository.
#
#   tools/export_clean.sh <new-remote-url> [branch]
#
# It refuses to export when a tracked file contains a string from the deny list below or looks like a secret.
set -euo pipefail
REMOTE="${1:?usage: tools/export_clean.sh <new-remote-url> [branch]}"
BRANCH="${2:-main}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Deny-listed strings (names, internal hosts, private folders) live in the git-ignored tools/.export-deny, one regex per line.
if [ ! -s tools/.export-deny ]; then echo "refusing: create tools/.export-deny with the strings that must never be published" >&2; exit 1; fi
DENY="$(grep -v -e '^#' -e '^$' tools/.export-deny | paste -sd'|' -)"
SECRET='(sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
if git ls-files -z -- . ":(exclude)tools/export_clean.sh" | xargs -0 grep -I -n -i -E "$DENY" -- 2>/dev/null; then
  echo "refusing: deny-listed strings above" >&2; exit 1
fi
if git ls-files -z -- . ":(exclude)tools/export_clean.sh" | xargs -0 grep -I -n -E "$SECRET" -- 2>/dev/null; then
  echo "refusing: something that looks like a secret above" >&2; exit 1
fi

TMP="$(mktemp -d)"
git archive --format=tar HEAD | tar -x -C "$TMP"
cd "$TMP"
git init -q -b "$BRANCH"
git add -A
# Fixed public identity: the GitHub noreply address of the repository owner, never the local git identity.
OWNER="$(printf '%s' "$REMOTE" | sed -E 's#.*github\.com[:/]([^/]+)/.*#\1#')"
git -c user.name="$OWNER" -c user.email="$OWNER@users.noreply.github.com" \
    commit -q -m "Marketing OSINT: cited marketing dossiers on any company from public data"
git remote add origin "$REMOTE"
echo "clean tree with $(git ls-files | wc -l) files in one commit at $TMP"
echo "push with: git -C $TMP push -u origin $BRANCH"
