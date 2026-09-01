#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

VERIFIER="$ROOT_DIR/scripts/verify-envelope.py"
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

VALID_ENVELOPE="$TEST_DIR/valid-envelope.json"
ALTERED_ENVELOPE="$TEST_DIR/altered-envelope.json"
NONCANONICAL_ENVELOPE="$TEST_DIR/noncanonical-envelope.json"

uv run \
  --with 'cryptography==50.0.1' \
  python - <<'PY' >"$VALID_ENVELOPE"
import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MULTICODEC_ED25519 = b"\xed\x01"


def base58btc_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""

    while number:
        number, remainder = divmod(number, 58)
        encoded = B58[remainder] + encoded

    leading_zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    return ("1" * leading_zeroes) + encoded


key = Ed25519PrivateKey.generate()
public_key = key.public_key().public_bytes_raw()
did = "did:key:z" + base58btc_encode(MULTICODEC_ED25519 + public_key)

room = "lobby"
nonce = "123456789"
text = "temporary verifier test"
canonical = f"{room}|{nonce}|{text}".encode("utf-8")

signature = (
    base64.urlsafe_b64encode(key.sign(canonical))
    .decode("ascii")
    .rstrip("=")
)

json.dump(
    {
        "room": room,
        "nonce": nonce,
        "text": text,
        "did": did,
        "sig": signature,
    },
    fp=__import__("sys").stdout,
)
PY

OUTPUT="$(
    uv run "$VERIFIER" <"$VALID_ENVELOPE"
)"

grep -Fq \
  "VALID: Ed25519 signature matches" \
  <<<"$OUTPUT" ||
    fail "valid temporary envelope was rejected"

pass "valid temporary envelope accepted"

CANONICAL_SIGNATURE="$(jq -r '.sig' "$VALID_ENVELOPE")"
FINAL_CHARACTER="${CANONICAL_SIGNATURE: -1}"

case "$FINAL_CHARACTER" in
    A) NONCANONICAL_FINAL="B" ;;
    Q) NONCANONICAL_FINAL="R" ;;
    g) NONCANONICAL_FINAL="h" ;;
    w) NONCANONICAL_FINAL="x" ;;
    *)
        fail "unexpected canonical signature ending: $FINAL_CHARACTER"
        ;;
esac

NONCANONICAL_SIGNATURE="$(
    printf '%s%s' \
      "${CANONICAL_SIGNATURE::-1}" \
      "$NONCANONICAL_FINAL"
)"

jq \
  --arg signature "$NONCANONICAL_SIGNATURE" \
  '.sig = $signature' \
  "$VALID_ENVELOPE" \
  >"$NONCANONICAL_ENVELOPE"

set +e

uv run "$VERIFIER" \
  <"$NONCANONICAL_ENVELOPE" \
  >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "noncanonical signature returned unexpected status $STATUS"

pass "noncanonical base64url signature rejected"

jq \
  '.text = "altered after signing"' \
  "$VALID_ENVELOPE" \
  >"$ALTERED_ENVELOPE"

set +e

uv run "$VERIFIER" \
  <"$ALTERED_ENVELOPE" \
  >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "altered envelope returned unexpected status $STATUS"

pass "altered message rejected"

jq \
  '.nonce = "123456790"' \
  "$VALID_ENVELOPE" \
  >"$ALTERED_ENVELOPE"

set +e

uv run "$VERIFIER" \
  <"$ALTERED_ENVELOPE" \
  >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "altered nonce returned unexpected status $STATUS"

pass "altered nonce rejected"

jq \
  '.room = "other-room"' \
  "$VALID_ENVELOPE" \
  >"$ALTERED_ENVELOPE"

set +e

uv run "$VERIFIER" \
  <"$ALTERED_ENVELOPE" \
  >/dev/null 2>&1

STATUS=$?

set -e

[ "$STATUS" -eq 1 ] ||
    fail "altered room returned unexpected status $STATUS"

pass "altered room rejected"

echo "All independent envelope-verification checks passed."
