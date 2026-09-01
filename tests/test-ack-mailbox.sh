#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

ACK_SCRIPT="$ROOT_DIR/scripts/ack-mailbox.sh"
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

bash -n "$ACK_SCRIPT" ||
    fail "acknowledgement script has invalid Bash syntax"

mkdir -p "$TEST_HOME/flop"
chmod 700 "$TEST_HOME/flop"

printf '%s\n' 1 >"$TEST_HOME/flop/mailbox.cursor"
printf '%s\n' 3 >"$TEST_HOME/flop/mailbox.pending"

chmod 600 \
  "$TEST_HOME/flop/mailbox.cursor" \
  "$TEST_HOME/flop/mailbox.pending"

if HOME="$TEST_HOME" "$ACK_SCRIPT" 2 >/dev/null 2>&1; then
    fail "incorrect acknowledgement was accepted"
fi

[ "$(<"$TEST_HOME/flop/mailbox.cursor")" = "1" ] ||
    fail "incorrect acknowledgement changed the cursor"

[ "$(<"$TEST_HOME/flop/mailbox.pending")" = "3" ] ||
    fail "incorrect acknowledgement changed the pending value"

pass "incorrect acknowledgement refused"

HOME="$TEST_HOME" "$ACK_SCRIPT" 3 >/dev/null

[ "$(jq -r '.cursor' "$TEST_HOME/flop/mailbox.cursor")" = "3" ] ||
    fail "exact acknowledgement did not advance the cursor"

[ "$(jq -r '.generation' "$TEST_HOME/flop/mailbox.cursor")" = "null" ] ||
    fail "legacy acknowledgement did not preserve unknown generation"

[ ! -e "$TEST_HOME/flop/mailbox.pending" ] ||
    fail "exact acknowledgement did not remove the pending file"

pass "exact acknowledgement accepted atomically"

jq -cn \
  '{generation: 2, cursor: 3}' \
  >"$TEST_HOME/flop/mailbox.cursor"

jq -cn \
  '{generation: 2, cursor: 4}' \
  >"$TEST_HOME/flop/mailbox.pending"

HOME="$TEST_HOME" "$ACK_SCRIPT" 4 >/dev/null

jq -e '
    .generation == 2
    and .cursor == 4
' "$TEST_HOME/flop/mailbox.cursor" >/dev/null ||
    fail "generation-aware acknowledgement wrote incorrect state"

pass "matching generation acknowledged atomically"

jq -cn \
  '{generation: 3, cursor: 5}' \
  >"$TEST_HOME/flop/mailbox.pending"

if HOME="$TEST_HOME" "$ACK_SCRIPT" 5 >/dev/null 2>&1; then
    fail "mismatched mailbox generation was acknowledged"
fi

jq -e '
    .generation == 2
    and .cursor == 4
' "$TEST_HOME/flop/mailbox.cursor" >/dev/null ||
    fail "generation mismatch changed cursor state"

rm -f "$TEST_HOME/flop/mailbox.pending"

pass "mismatched generation refused"

if HOME="$TEST_HOME" "$ACK_SCRIPT" 5 >/dev/null 2>&1; then
    fail "acknowledgement without a pending batch was accepted"
fi

jq -e '
    .generation == 2
    and .cursor == 4
' "$TEST_HOME/flop/mailbox.cursor" >/dev/null ||
    fail "missing-pending test changed the cursor"

pass "acknowledgement without pending batch refused"

echo "All acknowledgement regression checks passed."
