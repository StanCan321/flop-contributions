#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

POLL_SCRIPT="$ROOT_DIR/scripts/poll-mailbox.sh"
TEST_HOME="$(mktemp -d)"

cleanup() {
    rm -rf "$TEST_HOME"
}

trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

bash -n "$POLL_SCRIPT" ||
    fail "poller has invalid Bash syntax"

mkdir -p "$TEST_HOME/flop"
chmod 700 "$TEST_HOME/flop"

printf '%s\n' \
  'test-mailbox' \
  >"$TEST_HOME/flop/mailbox.txt"

printf '%s\n' \
  'not-a-cursor' \
  >"$TEST_HOME/flop/mailbox.cursor"

chmod 600 \
  "$TEST_HOME/flop/mailbox.txt" \
  "$TEST_HOME/flop/mailbox.cursor"

set +e

HOME="$TEST_HOME" \
  "$POLL_SCRIPT" \
  >"$TEST_HOME/stdout" \
  2>"$TEST_HOME/stderr"

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "invalid cursor returned unexpected status $STATUS"

grep -Fq \
  'ERROR: invalid cursor' \
  "$TEST_HOME/stderr" ||
    fail "invalid cursor error was not reported"

if grep -Fq \
  'unbound variable' \
  "$TEST_HOME/stderr"; then
    fail "cursor was evaluated before assignment"
fi

pass "invalid cursor rejected after assignment"

MOCK_BIN="$TEST_HOME/bin"
MOCK_RESPONSE="$TEST_HOME/response.json"
mkdir -p "$MOCK_BIN"

cat >"$MOCK_BIN/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

OUTPUT_FILE=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        -o)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -w)
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

[ -n "$OUTPUT_FILE" ]
cp "$MOCK_RESPONSE" "$OUTPUT_FILE"
printf '200'
MOCK

chmod 700 "$MOCK_BIN/curl"
printf '%s\n' 7 >"$TEST_HOME/flop/mailbox.cursor"

jq -n '{
    room: "test-mailbox",
    count: 0,
    first_seq: null,
    last_seq: 7,
    messages: [],
    wait_held: true
}' >"$MOCK_RESPONSE"

OUTPUT="$(
    HOME="$TEST_HOME" \
    PATH="$MOCK_BIN:$PATH" \
    MOCK_RESPONSE="$MOCK_RESPONSE" \
      "$POLL_SCRIPT" 2>"$TEST_HOME/stderr"
)"

jq -e '
    .status == "ok"
    and .first_seq == null
    and .last_seq == 7
    and (.messages | length) == 0
' <<<"$OUTPUT" >/dev/null ||
    fail "valid empty response was not preserved"

[ ! -e "$TEST_HOME/flop/mailbox.pending" ] ||
    fail "empty response created a pending acknowledgement"

pass "empty response with null first_seq accepted"

jq -n '{
    room: "test-mailbox",
    count: 0,
    first_seq: null,
    last_seq: 7,
    messages: [],
    wait_held: false
}' >"$MOCK_RESPONSE"

set +e

HOME="$TEST_HOME" \
PATH="$MOCK_BIN:$PATH" \
MOCK_RESPONSE="$MOCK_RESPONSE" \
  "$POLL_SCRIPT" \
  >"$TEST_HOME/stdout" \
  2>"$TEST_HOME/stderr"

STATUS=$?

set -e

[ "$STATUS" -eq 75 ] ||
    fail "refused long poll returned unexpected status $STATUS"

grep -Fq \
  'long-poll slot was not held' \
  "$TEST_HOME/stderr" ||
    fail "refused long poll did not request backoff"

pass "refused long poll requests bounded backoff"

SIGNATURE="$(printf 'A%.0s' {1..86})"

jq -n \
  --arg signature "$SIGNATURE" '{
    room: "test-mailbox",
    count: 1,
    first_seq: 8,
    last_seq: 8,
    messages: [
        {
            seq: 8,
            from: "did:key:z6Mktest",
            ts: "2026-09-01T00:00:00.000000Z",
            text: "signed fixture",
            nonce: 123,
            sig: $signature
        }
    ]
}' >"$MOCK_RESPONSE"

OUTPUT="$(
    HOME="$TEST_HOME" \
    PATH="$MOCK_BIN:$PATH" \
    MOCK_RESPONSE="$MOCK_RESPONSE" \
      "$POLL_SCRIPT" 2>"$TEST_HOME/stderr"
)"

[ "$(jq -r '.messages[0].sig' <<<"$OUTPUT")" = "$SIGNATURE" ] ||
    fail "retained signature was dropped or changed"

[ "$(<"$TEST_HOME/flop/mailbox.pending")" = "8" ] ||
    fail "signed-message fixture did not record its pending cursor"

pass "retained signature preserved in poll output"

echo "All mailbox-state regression checks passed."
