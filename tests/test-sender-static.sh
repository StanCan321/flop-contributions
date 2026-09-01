#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

SENDER="$ROOT_DIR/scripts/send.sh"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

[ -f "$SENDER" ] || fail "sender is missing"
[ -x "$SENDER" ] || fail "sender is not executable"

bash -n "$SENDER" || fail "sender has invalid Bash syntax"
pass "Bash syntax"

grep -Fq "Content-Type: application/json" "$SENDER" ||
    fail "JSON content type is missing"

grep -Fq -- "--data-binary @-" "$SENDER" ||
    fail "POST body is not read from standard input"

pass "signed POST transport"

if grep -Fq "say-signed" "$SENDER"; then
    fail "signed GET route remains in sender"
fi

pass "signed GET route absent"

grep -Fq 'MESSAGE_SHA256=' "$SENDER" ||
    fail "message hash is not calculated"

grep -Fq 'MESSAGE_CHARS=' "$SENDER" ||
    fail "message length is not calculated"

if grep -Fq -- '--arg message "$TEXT"' "$SENDER"; then
    fail "full message is passed to the activity log"
fi

if grep -Fq 'message: $message' "$SENDER"; then
    fail "full message field remains in activity log"
fi

pass "message bodies excluded from activity log"

grep -Fq 'flock -x 8' "$SENDER" ||
    fail "nonce lock is missing"

grep -Fq '9223372036854775806' "$SENDER" ||
    fail "safe nonce ceiling is missing"

pass "persistent nonce controls"

if grep -Eq \
    'SIGN_SEED[[:space:]]*=[0-9a-fA-F]{64}' \
    "$SENDER"; then
    fail "literal private seed found"
fi

if grep -Eq \
    'did:key:z6Mk[A-Za-z0-9]{40,}' \
    "$SENDER"; then
    fail "literal public identity found"
fi

pass "no embedded identity material"

grep -Fq 'VERIFIER="$HOME/technocore-agent/verify-envelope.py"' "$SENDER" ||
    fail "local envelope verifier path is missing"

grep -Fq 'requirements-verifier.txt' "$SENDER" ||
    fail "sender does not require the installed dependency lock"

grep -Fq 'UV_OFFLINE=1 uv run' "$SENDER" ||
    fail "sender does not force offline dependency execution"

grep -Fq '"$VERIFIER" >/dev/null' "$SENDER" ||
    fail "sender does not invoke the local verifier"

grep -Fq "local signature verification failed" "$SENDER" ||
    fail "sender does not fail closed after verification failure"

pass "local signature verification required"

echo "All static sender checks passed."
