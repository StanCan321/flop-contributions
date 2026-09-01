#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [AGENT_DIR [CHECKSUM_FILE]]" >&2
    exit 2
fi

AGENT_DIR="${1:-$HOME/technocore-agent}"
CHECKSUM_FILE="${2:-$ROOT_DIR/evidence/local-script-checksums.sha256}"
EXPECTED_UID="$(id -u)"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -d "$AGENT_DIR" ] || fail "agent directory is missing: $AGENT_DIR"
[ ! -L "$AGENT_DIR" ] || fail "agent directory must not be a symbolic link"
[ -f "$CHECKSUM_FILE" ] || fail "checksum manifest is missing: $CHECKSUM_FILE"
[ ! -L "$CHECKSUM_FILE" ] || fail "checksum manifest must not be a symbolic link"

AGENT_UID="$(stat -c '%u' "$AGENT_DIR")"
[ "$AGENT_UID" = "$EXPECTED_UID" ] || fail "agent directory has an unexpected owner"

declare -A SEEN=()
COUNT=0

while IFS= read -r LINE || [ -n "$LINE" ]; do
    [ -n "$LINE" ] || fail "checksum manifest contains an empty line"

    if [[ ! "$LINE" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]([A-Za-z0-9._-]+)$ ]]; then
        fail "checksum manifest contains an invalid entry"
    fi

    EXPECTED_HASH="${BASH_REMATCH[1]}"
    NAME="${BASH_REMATCH[2]}"
    [ -z "${SEEN[$NAME]+x}" ] || fail "checksum manifest contains a duplicate: $NAME"
    SEEN["$NAME"]=1

    TARGET="$AGENT_DIR/$NAME"
    [ -f "$TARGET" ] || fail "installed file is missing: $NAME"
    [ ! -L "$TARGET" ] || fail "installed file must not be a symbolic link: $NAME"
    [ "$(stat -c '%u' "$TARGET")" = "$EXPECTED_UID" ] ||
        fail "installed file has an unexpected owner: $NAME"
    EXPECTED_MODE=700
    if [[ "$NAME" == *.txt ]]; then
        EXPECTED_MODE=600
    fi
    [ "$(stat -c '%a' "$TARGET")" = "$EXPECTED_MODE" ] ||
        fail "installed file must have mode $EXPECTED_MODE: $NAME"

    ACTUAL_HASH="$(sha256sum "$TARGET")"
    ACTUAL_HASH="${ACTUAL_HASH%% *}"
    [ "$ACTUAL_HASH" = "$EXPECTED_HASH" ] || fail "checksum mismatch: $NAME"

    printf 'OK: %s\n' "$NAME"
    COUNT=$((COUNT + 1))
done <"$CHECKSUM_FILE"

[ "$COUNT" -gt 0 ] || fail "checksum manifest contains no entries"
printf 'Verified %s installed files.\n' "$COUNT"
