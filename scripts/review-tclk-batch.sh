#!/usr/bin/env bash
set -euo pipefail
umask 077

AGENT_DIR="$HOME/technocore-agent"
STATE_DIR="$HOME/flop"
BATCH_FILE="$STATE_DIR/mailbox.batch.json"
REVIEW_RECEIPT="$STATE_DIR/mailbox.review.json"
TCLK_REPORT="$STATE_DIR/tclk.review.json"
ROOM_FILE="$STATE_DIR/mailbox.txt"
VALIDATOR="$AGENT_DIR/validate-tclk-transcript.py"
DEPENDENCY_LOCK="$AGENT_DIR/requirements-verifier.txt"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_private_file() {
    local path="$1"
    local label="$2"
    [ -f "$path" ] || fail "$label must be a regular file"
    [ ! -L "$path" ] || fail "$label must not be a symbolic link"
    [ "$(stat -c '%u' "$path")" = "$(id -u)" ] ||
        fail "$label must be owned by the current user"
    [ $((8#$(stat -c '%a' "$path") & 8#077)) -eq 0 ] ||
        fail "$label must not be accessible by group or other users"
}

[ "$#" -eq 0 ] || fail "usage: $0"
[ -d "$STATE_DIR" ] || fail "private state directory is missing"
[ ! -L "$STATE_DIR" ] || fail "private state directory must not be a symbolic link"
[ "$(stat -c '%u' "$STATE_DIR")" = "$(id -u)" ] ||
    fail "private state directory must be owned by the current user"

require_private_file "$BATCH_FILE" "saved mailbox batch"
require_private_file "$REVIEW_RECEIPT" "trusted mailbox review receipt"
require_private_file "$ROOM_FILE" "mailbox capability file"
require_private_file "$DEPENDENCY_LOCK" "verified dependency lock"
require_private_file "$VALIDATOR" "installed tclk validator"
[ -x "$VALIDATOR" ] || fail "installed tclk validator is not executable"

ROOM="$(<"$ROOM_FILE")"
[[ "$ROOM" =~ ^[a-z0-9][a-z0-9_-]{0,47}$ ]] ||
    fail "mailbox capability file contains an invalid room name"

# The generic trusted review must describe this exact saved batch before the
# protocol-specific pass is allowed to run.
jq -e --slurpfile receipt "$REVIEW_RECEIPT" '
    ($receipt | length) == 1
    and .status == "ok"
    and .generation == $receipt[0].generation
    and .starting_cursor == $receipt[0].starting_cursor
    and .proposed_cursor == $receipt[0].proposed_cursor
    and .count == $receipt[0].count
    and $receipt[0].signature_status == "all_valid"
    and $receipt[0].ack_eligible == true
    and $receipt[0].ack_cursor == .proposed_cursor
' "$BATCH_FILE" >/dev/null ||
    fail "trusted review receipt does not match the saved mailbox batch"

[ ! -L "$TCLK_REPORT" ] || fail "tclk report path must not be a symbolic link"
TMP_REPORT="$(mktemp "$STATE_DIR/.tclk.review.XXXXXX")"
cleanup() {
    if [ -n "${TMP_REPORT:-}" ] && [ -e "$TMP_REPORT" ]; then
        find "$TMP_REPORT" -delete
    fi
}
trap cleanup EXIT

UV_OFFLINE=1 uv run \
  --python 3.12 \
  --with-requirements "$DEPENDENCY_LOCK" \
  "$VALIDATOR" \
  --room "$ROOM" \
  "$BATCH_FILE" \
  >"$TMP_REPORT"

chmod 600 "$TMP_REPORT"
mv -f "$TMP_REPORT" "$TCLK_REPORT"
TMP_REPORT=""
trap - EXIT

echo "Read-only tclk report recorded: $TCLK_REPORT"
echo "Mailbox cursor unchanged; no message or acknowledgement was sent"
