#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

TEST_DIR="$(mktemp -d)"
AGENT_DIR="$TEST_DIR/agent"
MANIFEST="$TEST_DIR/checksums.sha256"

cleanup() {
    find "$TEST_DIR" -depth -delete
}

trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

mkdir -m 700 "$AGENT_DIR"
install -m 700 "$ROOT_DIR/scripts/send.sh" "$AGENT_DIR/send.sh"
install -m 700 "$ROOT_DIR/scripts/verify-envelope.py" "$AGENT_DIR/verify-envelope.py"

(
    cd "$AGENT_DIR"
    sha256sum send.sh verify-envelope.py
) >"$MANIFEST"

"$ROOT_DIR/scripts/verify-installation.sh" "$AGENT_DIR" "$MANIFEST" >/dev/null ||
    fail "valid installation was refused"
pass "valid installation accepted"

printf '\n# tampered\n' >>"$AGENT_DIR/send.sh"
if "$ROOT_DIR/scripts/verify-installation.sh" "$AGENT_DIR" "$MANIFEST" >/dev/null 2>&1; then
    fail "tampered installation was accepted"
fi
pass "checksum mismatch refused"

install -m 700 "$ROOT_DIR/scripts/send.sh" "$AGENT_DIR/send.sh"
chmod 744 "$AGENT_DIR/send.sh"
if "$ROOT_DIR/scripts/verify-installation.sh" "$AGENT_DIR" "$MANIFEST" >/dev/null 2>&1; then
    fail "unsafe file mode was accepted"
fi
pass "unsafe file mode refused"

chmod 700 "$AGENT_DIR/send.sh"
mv "$AGENT_DIR/send.sh" "$TEST_DIR/real-send.sh"
ln -s "$TEST_DIR/real-send.sh" "$AGENT_DIR/send.sh"
if "$ROOT_DIR/scripts/verify-installation.sh" "$AGENT_DIR" "$MANIFEST" >/dev/null 2>&1; then
    fail "symbolic-link installation was accepted"
fi
pass "symbolic-link installation refused"

rm "$AGENT_DIR/send.sh"
install -m 700 "$ROOT_DIR/scripts/send.sh" "$AGENT_DIR/send.sh"
printf '%s\n' 'invalid manifest entry' >>"$MANIFEST"
if "$ROOT_DIR/scripts/verify-installation.sh" "$AGENT_DIR" "$MANIFEST" >/dev/null 2>&1; then
    fail "malformed checksum manifest was accepted"
fi
pass "malformed checksum manifest refused"

echo "All installation-verifier checks passed."
