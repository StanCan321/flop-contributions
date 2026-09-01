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

echo "All mailbox-state regression checks passed."
