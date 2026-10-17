#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"
PROBE="$ROOT_DIR/scripts/probe-technocore-compression.sh"
TEST_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TEST_DIR"
}

trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

mkdir -p "$TEST_DIR/bin"

cat >"$TEST_DIR/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

encoding=identity
headers=
output=
url=

while [ "$#" -gt 0 ]; do
    case "$1" in
        -H)
            case "$2" in
                "Accept-Encoding: "*) encoding="${2#Accept-Encoding: }" ;;
            esac
            shift 2
            ;;
        -D)
            headers="$2"
            shift 2
            ;;
        -o)
            output="$2"
            shift 2
            ;;
        --proto|--connect-timeout|--max-time|--max-filesize)
            shift 2
            ;;
        --tlsv1.2|--compressed|-fsS)
            shift
            ;;
        *)
            url="$1"
            shift
            ;;
    esac
done

[ -n "$headers" ] && [ -n "$output" ] && [ -n "$url" ]

{
    printf 'HTTP/2 200\r\n'
    printf 'Vary: Accept, Accept-Encoding\r\n'
    if [ "$encoding" != identity ]; then
        printf 'Content-Encoding: %s\r\n' "$encoding"
    fi
    printf '\r\n'
} >"$headers"

if [[ "$url" == */config ]]; then
    printf '{"version":"%s"}\n' "${MOCK_VERSION:-0.14.5}" >"$output"
elif [[ "$url" == *'?format=json&limit=1' ]]; then
    printf '{"last_seq":6}\n' >"$output"
elif [[ "$url" == */export ]]; then
    if [ "${MOCK_TRUNCATED:-}" = 1 ]; then
        printf '{"seq":5}\n' >"$output"
    else
        printf '{"seq":6}\n' >"$output"
    fi
elif [ "${MOCK_CORRUPT:-}" = "$encoding" ]; then
    printf 'altered decoded bytes\n' >"$output"
else
    printf 'identical decoded bytes\n' >"$output"
fi
MOCK

chmod 700 "$TEST_DIR/bin/curl"

PATH="$TEST_DIR/bin:$PATH" "$PROBE" 0.14.5 public-room >"$TEST_DIR/output"
grep -Fq 'Service version: 0.14.5' "$TEST_DIR/output" ||
    fail "matching service version was not reported"
grep -Fq '"resource": "docs"' "$TEST_DIR/output" ||
    fail "documentation compression was not checked"
grep -Fq '"resource": "export"' "$TEST_DIR/output" ||
    fail "export compression was not checked"
grep -Fq 'Export completeness: each decoded snapshot reaches pre-export last_seq 6.' \
    "$TEST_DIR/output" ||
    fail "export completeness was not checked"

set +e
PATH="$TEST_DIR/bin:$PATH" MOCK_VERSION=0.13.0 \
    "$PROBE" 0.14.5 >"$TEST_DIR/mismatch.out" 2>"$TEST_DIR/mismatch.err"
status=$?
set -e

[ "$status" -eq 3 ] || fail "wrong service version did not stop with status 3"
grep -Fq 'expected Technocore 0.14.5, observed 0.13.0' "$TEST_DIR/mismatch.err" ||
    fail "wrong service version was not explained"

set +e
PATH="$TEST_DIR/bin:$PATH" MOCK_CORRUPT=br \
    "$PROBE" 0.14.5 >"$TEST_DIR/corrupt.out" 2>"$TEST_DIR/corrupt.err"
status=$?
set -e

[ "$status" -eq 1 ] || fail "decoded-byte drift was not refused"
grep -Fq 'Brotli decoded bytes differ from identity' "$TEST_DIR/corrupt.err" ||
    fail "decoded-byte drift was not explained"

set +e
PATH="$TEST_DIR/bin:$PATH" MOCK_TRUNCATED=1 \
    "$PROBE" 0.14.5 public-room >"$TEST_DIR/truncated.out" 2>"$TEST_DIR/truncated.err"
status=$?
set -e

[ "$status" -eq 1 ] || fail "truncated export was not refused"
grep -Fq 'export identity ends at seq 5 before pre-export head 6' \
    "$TEST_DIR/truncated.err" ||
    fail "truncated export was not explained"

if rg -n 'curl.+-X|--request|--data|/say|/set|/ack' "$PROBE"; then
    fail "probe contains a write-capable curl pattern"
fi

echo "PASS: v0.14 compression probe is version-gated, complete, byte-exact and read-only"
