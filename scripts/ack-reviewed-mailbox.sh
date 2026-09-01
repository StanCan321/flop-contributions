#!/usr/bin/env bash
set -euo pipefail
umask 077

AGENT_DIR="$HOME/technocore-agent"
STATE_DIR="$HOME/flop"
BATCH_FILE="$STATE_DIR/mailbox.batch.json"
RECEIPT_FILE="$STATE_DIR/mailbox.review.json"
HISTORY_DIR="$STATE_DIR/reviewed-batches"
REVIEWER="$AGENT_DIR/review-mailbox-batch.py"
ACK_SCRIPT="$AGENT_DIR/ack-mailbox.sh"

if [ -L "$STATE_DIR" ]; then
    echo "ERROR: private state directory must not be a symlink" >&2
    exit 1
fi

if [ "$#" -ne 1 ] || [ "$1" != "--confirm-reviewed" ]; then
    echo "Usage: $0 --confirm-reviewed" >&2
    echo "This command advances the mailbox cursor after explicit operator review" >&2
    exit 2
fi

if [ ! -x "$REVIEWER" ] || [ ! -x "$ACK_SCRIPT" ]; then
    echo "ERROR: reviewer or acknowledgement script is missing or not executable" >&2
    exit 1
fi

if [ ! -f "$BATCH_FILE" ] || [ ! -f "$RECEIPT_FILE" ] \
   || [ -L "$BATCH_FILE" ] || [ -L "$RECEIPT_FILE" ]; then
    echo "ERROR: a regular saved batch and matching receipt are required" >&2
    exit 1
fi

# Re-run the fail-closed review. An existing receipt is accepted only if its
# exact deterministic bytes still match the saved batch.
uv run \
  --python 3.12 \
  --with 'cryptography==50.0.1' \
  "$REVIEWER" \
  --batch "$BATCH_FILE" \
  --receipt "$RECEIPT_FILE" \
  >/dev/null

if [ "$(jq -r '.ack_eligible' "$RECEIPT_FILE")" != "true" ]; then
    echo "ERROR: reviewed batch is not eligible for acknowledgement" >&2
    exit 1
fi

CURSOR="$(jq -r '.ack_cursor' "$RECEIPT_FILE")"
GENERATION="$(jq -r '.generation' "$RECEIPT_FILE")"

mkdir -p "$HISTORY_DIR"
chmod 700 "$HISTORY_DIR"
ARCHIVE="$HISTORY_DIR/${GENERATION}-${CURSOR}.json"

if [ -e "$ARCHIVE" ] && ! cmp -s "$RECEIPT_FILE" "$ARCHIVE"; then
    echo "ERROR: archived receipt conflicts with the reviewed batch" >&2
    exit 1
fi

"$ACK_SCRIPT" "$CURSOR"

if [ -e "$ARCHIVE" ]; then
    rm -f "$RECEIPT_FILE"
else
    mv "$RECEIPT_FILE" "$ARCHIVE"
fi

chmod 600 "$ARCHIVE"
rm -f "$BATCH_FILE"

echo "Reviewed batch acknowledged and redacted receipt archived: $ARCHIVE"
