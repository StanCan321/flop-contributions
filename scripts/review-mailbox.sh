#!/usr/bin/env bash
set -euo pipefail
umask 077

AGENT_DIR="$HOME/technocore-agent"
STATE_DIR="$HOME/flop"
BATCH_FILE="$STATE_DIR/mailbox.batch.json"
RECEIPT_FILE="$STATE_DIR/mailbox.review.json"
PENDING_FILE="$STATE_DIR/mailbox.pending"
POLL_SCRIPT="$AGENT_DIR/poll-mailbox.sh"
REVIEWER="$AGENT_DIR/review-mailbox-batch.py"

if [ -L "$STATE_DIR" ]; then
    echo "ERROR: private state directory must not be a symlink" >&2
    exit 1
fi

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

if [ ! -x "$POLL_SCRIPT" ] || [ ! -x "$REVIEWER" ]; then
    echo "ERROR: poller or batch reviewer is missing or not executable" >&2
    exit 1
fi

if [ -L "$BATCH_FILE" ] || [ -L "$RECEIPT_FILE" ]; then
    echo "ERROR: saved batch and receipt paths must not be symlinks" >&2
    exit 1
fi

if [ ! -e "$BATCH_FILE" ]; then
    if [ -e "$PENDING_FILE" ]; then
        echo "ERROR: acknowledgement is pending but the saved batch is missing" >&2
        echo "Do not acknowledge; recover the batch by deliberate duplicate delivery" >&2
        exit 1
    fi

    TMP_BATCH="$(mktemp "$STATE_DIR/.mailbox.batch.XXXXXX")"
    trap 'rm -f "$TMP_BATCH"' EXIT

    set +e
    "$POLL_SCRIPT" >"$TMP_BATCH"
    POLL_STATUS=$?
    set -e

    if [ "$POLL_STATUS" -ne 0 ]; then
        exit "$POLL_STATUS"
    fi

    chmod 600 "$TMP_BATCH"
    mv -f "$TMP_BATCH" "$BATCH_FILE"
    trap - EXIT
fi

chmod 600 "$BATCH_FILE"

uv run \
  --python 3.12 \
  --with 'cryptography==50.0.1' \
  "$REVIEWER" \
  --batch "$BATCH_FILE" \
  --receipt "$RECEIPT_FILE"

chmod 600 "$RECEIPT_FILE"

COUNT="$(jq -r '.count' "$RECEIPT_FILE")"

if [ "$COUNT" -eq 0 ]; then
    rm -f "$BATCH_FILE" "$RECEIPT_FILE"
    echo "No messages required review; no acknowledgement is pending"
    exit 0
fi

if [ ! -s "$PENDING_FILE" ]; then
    echo "ERROR: reviewed messages have no pending acknowledgement state" >&2
    exit 1
fi

echo "Batch verified and redacted receipt recorded: $RECEIPT_FILE"
echo "Raw batch retained privately for operator review: $BATCH_FILE"
echo "No acknowledgement was sent"
