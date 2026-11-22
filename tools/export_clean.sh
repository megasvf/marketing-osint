#!/usr/bin/env bash
# Export the current tree as ONE commit with no history, ready to push to a fresh (public) repository.
# The history and the internal files stay in the private repository.
#
#   tools/export_clean.sh <new-remote-url> [branch]
#
# Internal files may be force-added in the private repo (data/, output/, public/, docs/internal/ ...). They match
# .gitignore, so every tracked-but-ignored path is left out. The export refuses to run when an exported file contains
# a string from the private deny list (tools/.export-deny) or something that looks like a secret.
set -euo pipefail
REMOTE="${1:?usage: tools/export_clean.sh <new-remote-url> [branch]}"
BRANCH="${2:-main}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [ ! -s tools/.export-deny ]; then echo "refusing: create tools/.export-deny with the strings that must never be published" >&2; exit 1; fi
DENY="$(grep -v -e '^#' -e '^$' tools/.export-deny | paste -sd'|' -)"
SECRET='(sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

LIST="$(mktemp)"
git ls-files -ci --exclude-standard | sort > "$LIST.ignored"
git ls-files | sort | comm -23 - "$LIST.ignored" > "$LIST"
echo "exporting $(wc -l < "$LIST") files, leaving out $(wc -l < "$LIST.ignored") internal (git-ignored) files"
SCAN="$(grep -v -x 'tools/export_clean.sh' "$LIST")"
if printf '%s\n' "$SCAN" | tr '\n' '\0' | xargs -0 grep -I -n -i -E "$DENY" -- 2>/dev/null; then
  echo "refusing: deny-listed strings above" >&2; exit 1
fi
if printf '%s\n' "$SCAN" | tr '\n' '\0' | xargs -0 grep -I -n -E "$SECRET" -- 2>/dev/null; then
  echo "refusing: something that looks like a secret above" >&2; exit 1
fi

TMP="$(mktemp -d)"
tr '\n' '\0' < "$LIST" | xargs -0 git archive --format=tar HEAD -- | tar -x -C "$TMP"
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
