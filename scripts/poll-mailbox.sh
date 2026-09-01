#!/usr/bin/env bash
set -euo pipefail
umask 077

STATE_DIR="$HOME/flop"
MAILBOX_FILE="$STATE_DIR/mailbox.txt"
CURSOR_FILE="$STATE_DIR/mailbox.cursor"
LOCK_FILE="$STATE_DIR/mailbox.poll.lock"
PENDING_FILE="$STATE_DIR/mailbox.pending"

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

# Prevent simultaneous polls from returning the same batch.
exec 9>"$LOCK_FILE"
flock -x 9

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

if [ ! -s "$MAILBOX_FILE" ]; then
    echo "ERROR: mailbox file missing or empty" >&2
    exit 1
fi

MAILBOX="$(<"$MAILBOX_FILE")"

if [ -e "$PENDING_FILE" ]; then
    echo "ERROR: an earlier mailbox batch is still pending acknowledgement" >&2
    echo "Pending file: $PENDING_FILE" >&2
    echo "Process and acknowledge that batch before polling again" >&2
    exit 76
fi

if [ -s "$CURSOR_FILE" ]; then
    CURSOR="$(<"$CURSOR_FILE")"
else
    CURSOR=0
fi

if [[ ! "$CURSOR" =~ ^[0-9]{1,16}$ ]] ||
   [ "$CURSOR" -gt 9007199254740991 ]; then
    echo "ERROR: invalid cursor" >&2
    exit 1
fi

HTTP="$(
    curl \
        --connect-timeout 10 \
        --max-time 20 \
        --proto '=https' \
        --tlsv1.2 \
        -sS \
        -o "$TMP_FILE" \
        -w '%{http_code}' \
        "https://technocore.chat/r/$MAILBOX?since=$CURSOR&wait=10&format=json&n=$(date +%s%N)" \
        || true
)"

if [ "$HTTP" != "200" ]; then
    echo "Technocore unavailable: HTTP ${HTTP:-000}" >&2
    echo "Cursor unchanged: $CURSOR" >&2
    exit 75
fi

# Validate both JSON syntax and the fields subsequently used as integers.
if ! jq -e '
    (
        .first_seq == null
        or (
            (.first_seq | type) == "number"
            and (.first_seq | floor) == .first_seq
            and .first_seq >= 0
            and .first_seq <= 9007199254740991
        )
    )
    and (.last_seq | type) == "number"
    and (.last_seq | floor) == .last_seq
    and .last_seq >= 0
    and .last_seq <= 9007199254740991
    and (.messages | type) == "array"
    and (
        (has("wait_held") | not)
        or (.wait_held | type) == "boolean"
    )
    and all(
        .messages[];
        (.seq | type) == "number"
        and (.seq | floor) == .seq
        and .seq >= 0
        and .seq <= 9007199254740991
        and (.from | type) == "string"
        and (.ts | type) == "string"
        and (.text | type) == "string"
        and (
            (has("sig") | not)
            or (
                (.sig | type) == "string"
                and (.sig | test("^[A-Za-z0-9_-]{85}[AQgw]$"))
            )
        )
    )
' "$TMP_FILE" >/dev/null 2>&1; then
    echo "ERROR: Technocore returned invalid mailbox data" >&2
    echo "Cursor unchanged: $CURSOR" >&2
    exit 1
fi

FIRST_SEQ="$(jq -r '.first_seq // 0' "$TMP_FILE")"
LAST_SEQ="$(jq -r '.last_seq' "$TMP_FILE")"

WAIT_HELD="$(
    jq -r '
        if has("wait_held")
        then .wait_held
        else true
        end
    ' "$TMP_FILE"
)"

if [ "$WAIT_HELD" = "false" ]; then
    echo "Technocore long-poll slot was not held; backoff required" >&2
    echo "Cursor unchanged: $CURSOR" >&2
    exit 75
fi

if [ "$CURSOR" -gt 0 ] \
   && [ "$FIRST_SEQ" -gt 0 ] \
   && [ "$FIRST_SEQ" -gt $((CURSOR + 1)) ]; then

    jq -n \
        --argjson starting_cursor "$CURSOR" \
        --argjson first_seq "$FIRST_SEQ" \
        --argjson last_seq "$LAST_SEQ" \
        --argjson missing_from "$((CURSOR + 1))" \
        --argjson missing_to "$((FIRST_SEQ - 1))" \
        '{
            status: "history_gap",
            starting_cursor: $starting_cursor,
            first_available_seq: $first_seq,
            last_seq: $last_seq,
            missing_seq: {
                from: $missing_from,
                to: $missing_to
            },
            cursor_updated: false
        }'

    echo "WARNING: history gap detected; cursor not advanced" >&2
    exit 3
fi

jq \
    --argjson starting_cursor "$CURSOR" '
    {
        status: "ok",
        starting_cursor: $starting_cursor,
        proposed_cursor: .last_seq,
        count: (.messages | length),
        first_seq: .first_seq,
        last_seq: .last_seq,
        messages: [
            .messages[] |
            (
                {
                    seq: .seq,
                    from: .from,
                    ts: .ts,
                    nonce: .nonce,
                    text: .text
                }
                + (
                    if has("sig")
                    then {sig: .sig}
                    else {}
                    end
                )
            )
        ]
    }
' "$TMP_FILE"

if [ "$LAST_SEQ" -gt "$CURSOR" ]; then
    TMP_PENDING="$(mktemp "$STATE_DIR/.mailbox.pending.XXXXXX")"

    printf '%s\n' "$LAST_SEQ" >"$TMP_PENDING"
    chmod 600 "$TMP_PENDING"
    mv -f "$TMP_PENDING" "$PENDING_FILE"

    echo "Pending acknowledgement recorded: $LAST_SEQ" >&2
fi

echo "Cursor unchanged pending acknowledgement: $CURSOR" >&2
