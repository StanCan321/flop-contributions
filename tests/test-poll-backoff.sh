#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

BACKOFF_SCRIPT="$ROOT_DIR/scripts/poll-with-backoff.sh"
TEST_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TEST_DIR"
}

trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

bash -n "$BACKOFF_SCRIPT" ||
    fail "backoff wrapper has invalid Bash syntax"

SUCCESS_POLLER="$TEST_DIR/success-poller"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'echo "{\"status\":\"ok\",\"messages\":[]}"' \
  'exit 0' \
  >"$SUCCESS_POLLER"

chmod 700 "$SUCCESS_POLLER"

OUTPUT="$(
    POLL_SCRIPT="$SUCCESS_POLLER" \
    MAX_ATTEMPTS=2 \
    INITIAL_DELAY=1 \
    MAX_DELAY=1 \
      "$BACKOFF_SCRIPT" 2>/dev/null
)"

grep -Fq '"status":"ok"' <<<"$OUTPUT" ||
    fail "success output was not preserved"

pass "successful poll returned immediately"

FAILURE_POLLER="$TEST_DIR/failure-poller"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'echo "schema failure" >&2' \
  'exit 1' \
  >"$FAILURE_POLLER"

chmod 700 "$FAILURE_POLLER"

set +e

POLL_SCRIPT="$FAILURE_POLLER" \
MAX_ATTEMPTS=3 \
INITIAL_DELAY=1 \
MAX_DELAY=1 \
  "$BACKOFF_SCRIPT" >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "non-transient failure returned unexpected status $STATUS"

pass "non-transient failure was not retried"

PENDING_POLLER="$TEST_DIR/pending-poller"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'exit 76' \
  >"$PENDING_POLLER"

chmod 700 "$PENDING_POLLER"

set +e

POLL_SCRIPT="$PENDING_POLLER" \
MAX_ATTEMPTS=3 \
INITIAL_DELAY=1 \
MAX_DELAY=1 \
  "$BACKOFF_SCRIPT" >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 76 ] ||
    fail "pending-batch condition returned unexpected status $STATUS"

pass "pending batch stopped automatic retry"

GENERATION_POLLER="$TEST_DIR/generation-poller"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'exit 4' \
  >"$GENERATION_POLLER"

chmod 700 "$GENERATION_POLLER"

set +e

POLL_SCRIPT="$GENERATION_POLLER" \
MAX_ATTEMPTS=3 \
INITIAL_DELAY=1 \
MAX_DELAY=1 \
  "$BACKOFF_SCRIPT" >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 4 ] ||
    fail "generation change returned unexpected status $STATUS"

pass "generation change stopped automatic retry"

echo "All polling-backoff checks passed."
