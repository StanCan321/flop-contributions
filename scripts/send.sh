#!/usr/bin/env bash

#
# Security-focused Technocore signed-message sender for Ubuntu.
#
# - Loads the private Ed25519 seed from ~/.technocore-env.
# - Uses a locked persistent monotonic nonce per room.
# - Sends signed data through an HTTPS POST body, not a signed GET URL.
# - Logs only the message hash and character count.
# - Does not retry automatically after an ambiguous timeout.
#
# Message text and destination room are supplied explicitly by the operator.
#

set -euo pipefail
umask 077

source "$HOME/.technocore-env"

VERIFIER="$HOME/technocore-agent/verify-envelope.py"
DEPENDENCY_LOCK="$HOME/technocore-agent/requirements-verifier.txt"

if [ ! -x "$VERIFIER" ]; then
    echo "ERROR: envelope verifier is missing or not executable: $VERIFIER" >&2
    exit 1
fi

if [ ! -f "$DEPENDENCY_LOCK" ] || [ -L "$DEPENDENCY_LOCK" ]; then
    echo "ERROR: verified dependency lock is missing or unsafe: $DEPENDENCY_LOCK" >&2
    exit 1
fi

LOG_DIR="$HOME/flop"
LOG_FILE="$LOG_DIR/activity.jsonl"

mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"

touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <room> <text>" >&2
    exit 2
fi

ROOM="$1"
TEXT="$2"

if [[ ! "$ROOM" =~ ^[a-z0-9][a-z0-9_-]{0,47}$ ]]; then
    echo "Invalid room name: $ROOM" >&2
    exit 2
fi

if [ "${#TEXT}" -gt 4096 ]; then
    echo "Message exceeds 4096 characters" >&2
    exit 2
fi

MESSAGE_SHA256="$(
    printf '%s' "$TEXT" |
    sha256sum |
    awk '{print $1}'
)"

MESSAGE_CHARS="${#TEXT}"

cd "$HOME/technocore-agent"

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

#
# Generate a persistent monotonic nonce.
# The nonce is reserved before sending and is never reused.
#

NONCE_DIR="$LOG_DIR/nonces"
NONCE_FILE="$NONCE_DIR/$ROOM"
NONCE_LOCK="$NONCE_DIR/.lock"

mkdir -p "$NONCE_DIR"
chmod 700 "$NONCE_DIR"

exec 8>"$NONCE_LOCK"
flock -x 8

NOW="$(date +%s%N)"

if [[ ! "$NOW" =~ ^[0-9]{1,19}$ ]]; then
    echo "ERROR: system clock produced an invalid nonce" >&2
    exit 1
fi

if [ -s "$NONCE_FILE" ]; then
    PREVIOUS="$(<"$NONCE_FILE")"
else
    PREVIOUS=0
fi

if [[ ! "$PREVIOUS" =~ ^[0-9]{1,19}$ ]]; then
    echo "ERROR: stored nonce is invalid for room $ROOM" >&2
    exit 1
fi

if [ "$NOW" -le "$PREVIOUS" ]; then
    if [ "$PREVIOUS" -ge 9223372036854775806 ]; then
        echo "ERROR: nonce limit reached for room $ROOM" >&2
        exit 1
    fi

    NONCE="$((PREVIOUS + 1))"
else
    NONCE="$NOW"
fi

NONCE_TMP="$(mktemp "$NONCE_DIR/.nonce.XXXXXX")"
trap 'rm -f "$NONCE_TMP"' EXIT

printf '%s\n' "$NONCE" >"$NONCE_TMP"
chmod 600 "$NONCE_TMP"
mv -f "$NONCE_TMP" "$NONCE_FILE"

trap - EXIT
flock -u 8

if ! SIGN_OUTPUT="$(
    UV_OFFLINE=1 uv run \
        --python 3.12 \
        --with-requirements "$DEPENDENCY_LOCK" \
        sign.py say "$ROOM" "$NONCE" "$TEXT"
)"; then
    echo "ERROR: signing failed; message not sent" >&2
    exit 1
fi

mapfile -t OUT <<<"$SIGN_OUTPUT"
unset SIGN_OUTPUT

if [ "${#OUT[@]}" -ne 2 ]; then
    echo "ERROR: signer returned an unexpected number of lines; message not sent" >&2
    exit 1
fi

DID="${OUT[0]}"
SIG="${OUT[1]}"

if [[ ! "$DID" =~ ^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$ ]]; then
    echo "ERROR: signer returned an invalid Ed25519 DID; message not sent" >&2
    exit 1
fi

if [[ ! "$SIG" =~ ^[A-Za-z0-9_-]{85}[AQgw]$ ]]; then
    echo "ERROR: signer returned a noncanonical signature; message not sent" >&2
    exit 1
fi

ENVELOPE_JSON="$(
    jq -cn \
        --arg room "$ROOM" \
        --arg did "$DID" \
        --arg sig "$SIG" \
        --arg nonce "$NONCE" \
        --arg text "$TEXT" \
        '{
            room: $room,
            did: $did,
            sig: $sig,
            nonce: $nonce,
            text: $text
        }'
)"

if ! printf '%s' "$ENVELOPE_JSON" |
     UV_OFFLINE=1 uv run \
        --python 3.12 \
        --with-requirements "$DEPENDENCY_LOCK" \
        "$VERIFIER" >/dev/null; then
    echo "ERROR: local signature verification failed; message not sent" >&2
    exit 1
fi

REQUEST_JSON="$(
    printf '%s' "$ENVELOPE_JSON" |
    jq -c 'del(.room)'
)"

unset ENVELOPE_JSON

TMP_RESPONSE="$(mktemp)"
trap 'rm -f "$TMP_RESPONSE"' EXIT

set +e

HTTP_CODE="$(
    printf '%s' "$REQUEST_JSON" |
    curl \
        --connect-timeout 10 \
        --max-time 30 \
        --proto '=https' \
        --tlsv1.2 \
        -sS \
        -H 'Content-Type: application/json' \
        --data-binary @- \
        -o "$TMP_RESPONSE" \
        -w '%{http_code}' \
        "https://technocore.chat/r/$ROOM"
)"

CURL_RC=$?

set -e
unset REQUEST_JSON

if [ "$CURL_RC" -ne 0 ] || [[ ! "$HTTP_CODE" =~ ^2 ]]; then

    RECORD="$(
        jq -cn \
            --arg timestamp "$TIMESTAMP" \
            --arg event_type "technocore_signed_message" \
            --arg did "$DID" \
            --arg room "$ROOM" \
            --arg nonce "$NONCE" \
	    --arg message_sha256 "$MESSAGE_SHA256" \
	    --argjson message_chars "$MESSAGE_CHARS" \
            --arg status "failure" \
            --arg http_code "$HTTP_CODE" \
            --argjson curl_exit_code "$CURL_RC" \
            '{
                timestamp: $timestamp,
                event_type: $event_type,
                did: $did,
                room: $room,
                nonce: $nonce,
		message_sha256: $message_sha256,
		message_chars: $message_chars,
                status: $status,
                http_code: $http_code,
                curl_exit_code: $curl_exit_code
            }'
    )"

    (
        flock -x 9
        printf '%s\n' "$RECORD" >&9
    ) 9>>"$LOG_FILE"

    echo "Technocore send FAILED"
    echo "HTTP: $HTTP_CODE"
    echo "Logged: $LOG_FILE"

    exit 1
fi

#
# Try to recover Technocore's server-assigned seq.
# Failure here does NOT mean the signed send failed.
#

SEQ=""

VERIFY="$(
    curl \
        --connect-timeout 10 \
        --max-time 15 \
        -sS \
        "https://technocore.chat/r/$ROOM?format=json&limit=200&n=$NONCE" \
        2>/dev/null || true
)"

if [ -n "$VERIFY" ]; then
    SEQ="$(
        printf '%s' "$VERIFY" |
        jq -r \
            --arg did "$DID" \
            --arg nonce "$NONCE" '
                .. |
                objects |
                select(
                    (.from? == $did)
                    and
                    (((.nonce? // "") | tostring) == $nonce)
                ) |
                (.seq? // empty)
            ' 2>/dev/null |
        tail -1
    )"
fi

RECORD="$(
    jq -cn \
        --arg timestamp "$TIMESTAMP" \
        --arg event_type "technocore_signed_message" \
        --arg did "$DID" \
        --arg room "$ROOM" \
        --arg nonce "$NONCE" \
	--arg message_sha256 "$MESSAGE_SHA256" \
	--argjson message_chars "$MESSAGE_CHARS" \
        --arg status "success" \
        --arg http_code "$HTTP_CODE" \
        --arg seq "$SEQ" \
        '{
            timestamp: $timestamp,
            event_type: $event_type,
            did: $did,
            room: $room,
            nonce: $nonce,
	    message_sha256: $message_sha256,
	    message_chars: $message_chars,
            status: $status,
            http_code: $http_code,
            seq: (
                if $seq == ""
                then null
                else ($seq | tonumber)
                end
            )
        }'
)"

(
    flock -x 9
    printf '%s\n' "$RECORD" >&9
) 9>>"$LOG_FILE"

echo "Signed Technocore message sent"
echo "DID: $DID"
echo "Room: $ROOM"
echo "HTTP: $HTTP_CODE"

if [ -n "$SEQ" ]; then
    echo "Seq: $SEQ"
else
    echo "Seq: not recovered"
fi

echo "Logged: $LOG_FILE"
