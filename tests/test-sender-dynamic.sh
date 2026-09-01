#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

SENDER="$ROOT_DIR/scripts/send.sh"
TEST_HOME="$(mktemp -d)"
MOCK_BIN="$TEST_HOME/bin"
AGENT_DIR="$TEST_HOME/technocore-agent"
CALLS_FILE="$TEST_HOME/curl.calls"
REQUEST_FILE="$TEST_HOME/request.json"

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

mkdir -p "$MOCK_BIN" "$AGENT_DIR"
chmod 700 "$TEST_HOME" "$MOCK_BIN" "$AGENT_DIR"

install -m 700 "$SENDER" "$AGENT_DIR/send.sh"

printf '%s\n' \
  '# test fixture: the mock signer does not read this value' \
  'SIGN_SEED=not-a-real-seed' \
  >"$TEST_HOME/.technocore-env"

chmod 600 "$TEST_HOME/.technocore-env"

printf '%s\n' '# mock signer target' >"$AGENT_DIR/sign.py"
printf '%s\n' '# mock verifier target' >"$AGENT_DIR/verify-envelope.py"
chmod 700 "$AGENT_DIR/verify-envelope.py"

cat >"$MOCK_BIN/uv" <<'MOCK_UV'
#!/usr/bin/env bash
set -euo pipefail

[ "$1" = "run" ]
shift

if [ "${1:-}" = "--python" ]; then
    shift 2
fi

TARGET="${1:-}"

if [ "$TARGET" = "sign.py" ]; then
    if [ "${MOCK_SIGN_STATUS:-0}" -ne 0 ]; then
        exit "$MOCK_SIGN_STATUS"
    fi

    if [ "${MOCK_SIGN_SHAPE:-valid}" = "short" ]; then
        printf '%s\n' 'one-line-only'
        exit 0
    fi

    printf 'did:key:z6Mk'
    printf '1%.0s' {1..44}
    printf '\n'
    printf 'A%.0s' {1..86}
    printf '\n'
    exit 0
fi

tee "$MOCK_VERIFIER_INPUT" >/dev/null
exit "${MOCK_VERIFY_STATUS:-0}"
MOCK_UV

cat >"$MOCK_BIN/curl" <<'MOCK_CURL'
#!/usr/bin/env bash
set -euo pipefail

OUTPUT_FILE=""
IS_POST=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        -o)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -w)
            shift 2
            ;;
        --data-binary)
            IS_POST=true
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [ "$IS_POST" = true ]; then
    printf '%s\n' POST >>"$MOCK_CALLS_FILE"
    tee "$MOCK_REQUEST_FILE" >/dev/null

    if [ -n "$OUTPUT_FILE" ]; then
        printf '%s\n' ok >"$OUTPUT_FILE"
    fi

    printf '%s' "${MOCK_HTTP_CODE:-200}"
    exit "${MOCK_CURL_STATUS:-0}"
fi

printf '%s\n' VERIFY >>"$MOCK_CALLS_FILE"
printf '%s\n' '{"messages":[]}'
MOCK_CURL

chmod 700 "$MOCK_BIN/uv" "$MOCK_BIN/curl"

run_sender() {
    HOME="$TEST_HOME" \
    PATH="$MOCK_BIN:$PATH" \
    MOCK_CALLS_FILE="$CALLS_FILE" \
    MOCK_REQUEST_FILE="$REQUEST_FILE" \
    MOCK_VERIFIER_INPUT="$TEST_HOME/verifier-input.json" \
    MOCK_SIGN_STATUS="${MOCK_SIGN_STATUS:-0}" \
    MOCK_SIGN_SHAPE="${MOCK_SIGN_SHAPE:-valid}" \
    MOCK_VERIFY_STATUS="${MOCK_VERIFY_STATUS:-0}" \
    MOCK_HTTP_CODE="${MOCK_HTTP_CODE:-200}" \
    MOCK_CURL_STATUS="${MOCK_CURL_STATUS:-0}" \
      "$AGENT_DIR/send.sh" test-room "$1"
}

MESSAGE='dynamic sender private body'

MOCK_SIGN_STATUS=1
set +e
run_sender "$MESSAGE" >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
STATUS=$?
set -e
unset MOCK_SIGN_STATUS

[ "$STATUS" -eq 1 ] || fail "signer failure returned status $STATUS"
[ ! -e "$CALLS_FILE" ] || fail "signer failure reached curl"
grep -Fq 'signing failed' "$TEST_HOME/stderr" || fail "signer failure was not reported"
pass "signer failure stopped transmission"

MOCK_SIGN_SHAPE=short
set +e
run_sender "$MESSAGE" >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
STATUS=$?
set -e
unset MOCK_SIGN_SHAPE

[ "$STATUS" -eq 1 ] || fail "malformed signer output returned status $STATUS"
[ ! -e "$CALLS_FILE" ] || fail "malformed signer output reached curl"
pass "malformed signer output stopped transmission"

MOCK_VERIFY_STATUS=1
set +e
run_sender "$MESSAGE" >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
STATUS=$?
set -e
unset MOCK_VERIFY_STATUS

[ "$STATUS" -eq 1 ] || fail "verifier failure returned status $STATUS"
[ ! -e "$CALLS_FILE" ] || fail "verifier failure reached curl"
FIRST_NONCE="$(<"$TEST_HOME/flop/nonces/test-room")"
pass "verifier failure stopped transmission after nonce reservation"

run_sender "$MESSAGE" >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
SECOND_NONCE="$(<"$TEST_HOME/flop/nonces/test-room")"

[ "$SECOND_NONCE" -gt "$FIRST_NONCE" ] || fail "reserved nonce was reused"
[ "$(grep -Fc POST "$CALLS_FILE")" -eq 1 ] || fail "successful send posted more than once"
[ "$(jq -r '.text' "$REQUEST_FILE")" = "$MESSAGE" ] || fail "POST body changed the message"

if grep -Fq "$MESSAGE" "$TEST_HOME/flop/activity.jsonl"; then
    fail "activity log retained the message body"
fi

jq -s -e '
    length == 1
    and .[0].status == "success"
    and (.[0].message_sha256 | test("^[0-9a-f]{64}$"))
    and .[0].message_chars > 0
' "$TEST_HOME/flop/activity.jsonl" >/dev/null || fail "success log record is invalid"

pass "successful POST used a fresh nonce and redacted log"

MOCK_HTTP_CODE=503
set +e
run_sender 'http failure body' >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
STATUS=$?
set -e
unset MOCK_HTTP_CODE

[ "$STATUS" -eq 1 ] || fail "HTTP failure returned status $STATUS"
[ "$(grep -Fc POST "$CALLS_FILE")" -eq 2 ] || fail "HTTP failure retried unexpectedly"

if grep -Fq 'http failure body' "$TEST_HOME/flop/activity.jsonl"; then
    fail "failure log retained the message body"
fi

jq -s -e '
    length == 2
    and .[1].status == "failure"
    and .[1].http_code == "503"
' "$TEST_HOME/flop/activity.jsonl" >/dev/null || fail "HTTP failure log record is invalid"

pass "HTTP failure was not retried and remained redacted"

MOCK_CURL_STATUS=28
MOCK_HTTP_CODE=000
set +e
run_sender 'ambiguous timeout body' >"$TEST_HOME/stdout" 2>"$TEST_HOME/stderr"
STATUS=$?
set -e
unset MOCK_CURL_STATUS MOCK_HTTP_CODE

[ "$STATUS" -eq 1 ] || fail "ambiguous timeout returned status $STATUS"
[ "$(grep -Fc POST "$CALLS_FILE")" -eq 3 ] || fail "ambiguous timeout retried unexpectedly"

pass "ambiguous timeout reserved once and was not retried"

echo "All dynamic sender checks passed."
