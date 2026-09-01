#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

TEST_HOME="$(mktemp -d)"
AGENT_DIR="$TEST_HOME/technocore-agent"
MOCK_BIN="$TEST_HOME/bin"
SERVER_STATE="$TEST_HOME/server.json"

cleanup() {
    find "$TEST_HOME" -depth -delete
}

trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

mkdir -p "$AGENT_DIR" "$MOCK_BIN" "$TEST_HOME/flop"
chmod 700 "$TEST_HOME" "$AGENT_DIR" "$MOCK_BIN" "$TEST_HOME/flop"

install -m 700 "$ROOT_DIR/scripts/send.sh" "$AGENT_DIR/send.sh"
install -m 700 "$ROOT_DIR/scripts/poll-mailbox.sh" "$AGENT_DIR/poll-mailbox.sh"
install -m 700 "$ROOT_DIR/scripts/ack-mailbox.sh" "$AGENT_DIR/ack-mailbox.sh"
install -m 700 "$ROOT_DIR/scripts/verify-envelope.py" "$AGENT_DIR/verify-envelope.py"

printf '%s\n' \
  '# local integration fixture; no real private key is used' \
  'SIGN_SEED=not-a-real-seed' \
  >"$TEST_HOME/.technocore-env"
chmod 600 "$TEST_HOME/.technocore-env"

printf '%s\n' '# mock signer target' >"$AGENT_DIR/sign.py"
printf '%s\n' 'test-room' >"$TEST_HOME/flop/mailbox.txt"
printf '%s\n' '{"generation":1,"next_seq":1,"messages":[]}' >"$SERVER_STATE"
chmod 600 "$TEST_HOME/flop/mailbox.txt" "$SERVER_STATE"

# The integration harness tests script orchestration. Cryptographic behavior is
# covered independently by test-envelope-verifier.sh.
install -m 700 "$ROOT_DIR/tests/fixtures/integration/uv" "$MOCK_BIN/uv"
install -m 700 "$ROOT_DIR/tests/fixtures/integration/curl" "$MOCK_BIN/curl"

chmod 700 "$MOCK_BIN/uv" "$MOCK_BIN/curl"

run_in_fixture() {
    HOME="$TEST_HOME" \
    PATH="$MOCK_BIN:$PATH" \
    MOCK_SERVER_STATE="$SERVER_STATE" \
      "$@"
}

MESSAGE='local integration private body'

run_in_fixture "$AGENT_DIR/send.sh" test-room "$MESSAGE" \
  >"$TEST_HOME/send.stdout" 2>"$TEST_HOME/send.stderr"

jq -e --arg text "$MESSAGE" '
    .next_seq == 2
    and (.messages | length) == 1
    and .messages[0].seq == 1
    and .messages[0].text == $text
' "$SERVER_STATE" >/dev/null || fail "signed POST was not stored by the local service"

pass "signed sender posted once to the local service"

run_in_fixture "$AGENT_DIR/poll-mailbox.sh" \
  >"$TEST_HOME/poll.json" 2>"$TEST_HOME/poll.stderr"

jq -e --arg text "$MESSAGE" '
    .status == "ok"
    and .generation == 1
    and .starting_cursor == 0
    and .proposed_cursor == 1
    and .count == 1
    and .messages[0].text == $text
' "$TEST_HOME/poll.json" >/dev/null || fail "poll did not return the posted message"

jq -e '.generation == 1 and .cursor == 1' \
  "$TEST_HOME/flop/mailbox.pending" >/dev/null ||
    fail "poll did not create the expected pending acknowledgement"

[ ! -e "$TEST_HOME/flop/mailbox.cursor" ] ||
    fail "poll advanced the cursor before acknowledgement"

pass "poll created a generation-aware pending batch without advancing"

if run_in_fixture "$AGENT_DIR/ack-mailbox.sh" 2 >/dev/null 2>&1; then
    fail "incorrect integration acknowledgement was accepted"
fi

run_in_fixture "$AGENT_DIR/ack-mailbox.sh" 1 \
  >"$TEST_HOME/ack.stdout" 2>"$TEST_HOME/ack.stderr"

jq -e '.generation == 1 and .cursor == 1' \
  "$TEST_HOME/flop/mailbox.cursor" >/dev/null ||
    fail "exact acknowledgement did not commit generation and cursor"

[ ! -e "$TEST_HOME/flop/mailbox.pending" ] ||
    fail "exact acknowledgement left a pending batch"

pass "exact acknowledgement committed the cursor atomically"

run_in_fixture "$AGENT_DIR/poll-mailbox.sh" \
  >"$TEST_HOME/empty-poll.json" 2>"$TEST_HOME/empty-poll.stderr"

jq -e '
    .status == "ok"
    and .generation == 1
    and .starting_cursor == 1
    and .proposed_cursor == 1
    and .count == 0
    and (.messages | length) == 0
' "$TEST_HOME/empty-poll.json" >/dev/null ||
    fail "follow-up poll did not resume from the acknowledged cursor"

[ ! -e "$TEST_HOME/flop/mailbox.pending" ] ||
    fail "empty follow-up poll created a pending batch"

if grep -Fq "$MESSAGE" "$TEST_HOME/flop/activity.jsonl"; then
    fail "activity log retained the integration message body"
fi

pass "follow-up poll resumed cleanly and the activity log stayed redacted"

echo "All local integration checks passed."
