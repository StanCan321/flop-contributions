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

PENDING_STATE="$(<"$PENDING_FILE")"
PENDING_GENERATION=null

if [[ "$PENDING_STATE" =~ ^[0-9]{1,16}$ ]]; then
    PENDING_CURSOR="$PENDING_STATE"
elif jq -e '
    (.cursor | type) == "number"
    and (.cursor | floor) == .cursor
    and .cursor >= 0
    and .cursor <= 9007199254740991
    and (
        .generation == null
        or (
            (.generation | type) == "number"
            and (.generation | floor) == .generation
            and .generation >= 0
            and .generation <= 9007199254740991
        )
    )
' <<<"$PENDING_STATE" >/dev/null 2>&1; then
    PENDING_CURSOR="$(jq -r '.cursor' <<<"$PENDING_STATE")"
    PENDING_GENERATION="$(jq -r '.generation // "null"' <<<"$PENDING_STATE")"
else
    echo "ERROR: pending acknowledgement file is invalid" >&2
    exit 1
fi

if [ "$NEW_CURSOR" -ne "$PENDING_CURSOR" ]; then
    echo "ERROR: acknowledgement does not match pending batch" >&2
    echo "Expected: $PENDING_CURSOR" >&2
    echo "Received: $NEW_CURSOR" >&2
    exit 1
fi

CURRENT_GENERATION=null

if [ -s "$CURSOR_FILE" ]; then
    CURRENT_STATE="$(<"$CURSOR_FILE")"

    if [[ "$CURRENT_STATE" =~ ^[0-9]{1,16}$ ]]; then
        CURRENT="$CURRENT_STATE"
    elif jq -e '
        (.cursor | type) == "number"
        and (.cursor | floor) == .cursor
        and .cursor >= 0
        and .cursor <= 9007199254740991
        and (
            .generation == null
            or (
                (.generation | type) == "number"
                and (.generation | floor) == .generation
                and .generation >= 0
                and .generation <= 9007199254740991
            )
        )
    ' <<<"$CURRENT_STATE" >/dev/null 2>&1; then
        CURRENT="$(jq -r '.cursor' <<<"$CURRENT_STATE")"
        CURRENT_GENERATION="$(jq -r '.generation // "null"' <<<"$CURRENT_STATE")"
    else
        echo "ERROR: stored cursor state is invalid" >&2
        exit 1
    fi
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

if [ "$CURRENT_GENERATION" != "null" ] \
   && [ "$PENDING_GENERATION" != "null" ] \
   && [ "$CURRENT_GENERATION" -ne "$PENDING_GENERATION" ]; then
    echo "ERROR: pending batch belongs to a different mailbox generation" >&2
    echo "Current generation: $CURRENT_GENERATION" >&2
    echo "Pending generation: $PENDING_GENERATION" >&2
    exit 1
fi

if [ "$PENDING_GENERATION" != "null" ]; then
    EFFECTIVE_GENERATION="$PENDING_GENERATION"
else
    EFFECTIVE_GENERATION="$CURRENT_GENERATION"
fi

TMP_CURSOR="$(mktemp "$STATE_DIR/.mailbox.cursor.XXXXXX")"
trap 'rm -f "$TMP_CURSOR"' EXIT

jq -cn \
    --argjson generation "$EFFECTIVE_GENERATION" \
    --argjson cursor "$NEW_CURSOR" \
    '{generation: $generation, cursor: $cursor}' \
    >"$TMP_CURSOR"
chmod 600 "$TMP_CURSOR"
mv -f "$TMP_CURSOR" "$CURSOR_FILE"
rm -f "$PENDING_FILE"
trap - EXIT

if [ "$NEW_CURSOR" -eq "$CURRENT" ]; then
    echo "Cursor unchanged and pending batch cleared: $CURRENT"
else
    echo "Cursor acknowledged: $CURRENT -> $NEW_CURSOR"
fi
