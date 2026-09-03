#!/usr/bin/env bash
set -euo pipefail
umask 077

REPOSITORY="flop-labs/tclk"
VECTOR_PATH="tests/vectors.test.ts"
REVIEWED_COMMIT="1459b78e3b981bbac67f845784c885b3b1ad85ba"
REVIEWED_SHA256="c60f109ba26547c6be0795b0eb66a861a96a7d68a36885a28f318e69a1cebb96"
API_URL="https://api.github.com/repos/$REPOSITORY/commits/main"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ "$#" -eq 0 ] || fail "usage: $0"
command -v curl >/dev/null || fail "curl is required"
command -v jq >/dev/null || fail "jq is required"
command -v sha256sum >/dev/null || fail "sha256sum is required"

TMP_DIR="$(mktemp -d)"
cleanup() { find "$TMP_DIR" -depth -delete; }
trap cleanup EXIT

curl --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
  --fail --silent --show-error \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "$API_URL" >"$TMP_DIR/commit.json"

CURRENT_COMMIT="$(jq -er '.sha' \
  "$TMP_DIR/commit.json")" || fail "upstream did not return one vector commit"
[[ "$CURRENT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "upstream returned an invalid commit"

RAW_URL="https://raw.githubusercontent.com/$REPOSITORY/$CURRENT_COMMIT/$VECTOR_PATH"
curl --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30 \
  --fail --silent --show-error "$RAW_URL" >"$TMP_DIR/vectors.test.ts"

CURRENT_SHA256="$(sha256sum "$TMP_DIR/vectors.test.ts")"
CURRENT_SHA256="${CURRENT_SHA256%% *}"

printf 'Reviewed vector commit: %s\n' "$REVIEWED_COMMIT"
printf 'Current vector commit:  %s\n' "$CURRENT_COMMIT"
printf 'Reviewed vector SHA-256: %s\n' "$REVIEWED_SHA256"
printf 'Current vector SHA-256:  %s\n' "$CURRENT_SHA256"

[ "$CURRENT_COMMIT" = "$REVIEWED_COMMIT" ] ||
  fail "upstream vector commit drifted; review changes manually"
[ "$CURRENT_SHA256" = "$REVIEWED_SHA256" ] ||
  fail "upstream vector content drifted; review changes manually"

echo "OK: upstream tclk golden vectors still match the reviewed constants"
