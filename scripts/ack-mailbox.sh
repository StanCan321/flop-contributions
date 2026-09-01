#!/usr/bin/env bash
set -euo pipefail
umask 077

STATE_DIR="$HOME/flop"
CURSOR_FILE="$STATE_DIR/mailbox.cursor"
LOCK_FILE="$STATE_DIR/mailbox.poll.lock"
PENDING_FILE="$STATE_DIR/mailbox.pending"

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <processed-last-seq>" >&2
    exit 2
fi

NEW_CURSOR="$1"

if [[ ! "$NEW_CURSOR" =~ ^[0-9]{1,16}$ ]] ||
   [ "$NEW_CURSOR" -gt 9007199254740991 ]; then
    echo "ERROR: acknowledgement must be a bounded nonnegative integer" >&2
    exit 2
fi

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

exec 9>"$LOCK_FILE"
flock -x 9

if [ ! -s "$PENDING_FILE" ]; then
    echo "ERROR: no mailbox batch is pending acknowledgement" >&2
    exit 1
fi

PENDING_CURSOR="$(<"$PENDING_FILE")"

if [[ ! "$PENDING_CURSOR" =~ ^[0-9]{1,16}$ ]] ||
   [ "$PENDING_CURSOR" -gt 9007199254740991 ]; then
    echo "ERROR: pending acknowledgement file is invalid" >&2
    exit 1
fi

if [ "$NEW_CURSOR" -ne "$PENDING_CURSOR" ]; then
    echo "ERROR: acknowledgement does not match pending batch" >&2
    echo "Expected: $PENDING_CURSOR" >&2
    echo "Received: $NEW_CURSOR" >&2
    exit 1
fi

if [ -s "$CURSOR_FILE" ]; then
    CURRENT="$(<"$CURSOR_FILE")"
else
    CURRENT=0
fi

if [[ ! "$CURRENT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: stored cursor is invalid" >&2
    exit 1
fi

if [ "$NEW_CURSOR" -lt "$CURRENT" ]; then
    echo "ERROR: refusing cursor regression: $CURRENT -> $NEW_CURSOR" >&2
    exit 1
fi

if [ "$NEW_CURSOR" -eq "$CURRENT" ]; then
    echo "Cursor unchanged: $CURRENT"
    exit 0
fi

TMP_CURSOR="$(mktemp "$STATE_DIR/.mailbox.cursor.XXXXXX")"
trap 'rm -f "$TMP_CURSOR"' EXIT

printf '%s\n' "$NEW_CURSOR" >"$TMP_CURSOR"
chmod 600 "$TMP_CURSOR"
mv -f "$TMP_CURSOR" "$CURSOR_FILE"
rm -f "$PENDING_FILE"
trap - EXIT

echo "Cursor acknowledged: $CURRENT -> $NEW_CURSOR"
