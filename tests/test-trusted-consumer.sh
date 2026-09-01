#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

TEST_HOME="$(mktemp -d)"
AGENT_DIR="$TEST_HOME/technocore-agent"
STATE_DIR="$TEST_HOME/flop"

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

mkdir -p "$AGENT_DIR" "$STATE_DIR"
chmod 700 "$TEST_HOME" "$AGENT_DIR" "$STATE_DIR"

install -m 700 "$ROOT_DIR/scripts/review-mailbox-batch.py" "$AGENT_DIR/review-mailbox-batch.py"
install -m 700 "$ROOT_DIR/scripts/review-mailbox.sh" "$AGENT_DIR/review-mailbox.sh"
install -m 700 "$ROOT_DIR/scripts/ack-reviewed-mailbox.sh" "$AGENT_DIR/ack-reviewed-mailbox.sh"
install -m 700 "$ROOT_DIR/scripts/verify-envelope.py" "$AGENT_DIR/verify-envelope.py"

printf '%s\n' test-room >"$STATE_DIR/mailbox.txt"
chmod 600 "$STATE_DIR/mailbox.txt"

cat >"$AGENT_DIR/poll-mailbox.sh" <<'MOCK_POLL'
#!/usr/bin/env bash
set -euo pipefail

cp "$MOCK_BATCH" /dev/stdout

if [ "$(jq -r '.count' "$MOCK_BATCH")" -gt 0 ]; then
    jq -c '{generation: .generation, cursor: .proposed_cursor}' \
      "$MOCK_BATCH" >"$HOME/flop/mailbox.pending"
    chmod 600 "$HOME/flop/mailbox.pending"
fi
MOCK_POLL

cat >"$AGENT_DIR/ack-mailbox.sh" <<'MOCK_ACK'
#!/usr/bin/env bash
set -euo pipefail

[ "$#" -eq 1 ]
[ -f "$HOME/flop/mailbox.pending" ]
[ "$(jq -r '.cursor' "$HOME/flop/mailbox.pending")" = "$1" ]
cp "$HOME/flop/mailbox.pending" "$HOME/flop/mailbox.cursor"
rm -f "$HOME/flop/mailbox.pending"
printf 'Cursor acknowledged: %s\n' "$1"
MOCK_ACK

chmod 700 "$AGENT_DIR/poll-mailbox.sh" "$AGENT_DIR/ack-mailbox.sh"

uv run \
  --with 'cryptography==50.0.1' \
  python - "$TEST_HOME" <<'PY'
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


root = Path(sys.argv[1])
alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = alphabet[remainder] + encoded
    zeroes = len(raw) - len(raw.lstrip(b"\0"))
    return ("1" * zeroes) + encoded


key = Ed25519PrivateKey.generate()
public = key.public_key().public_bytes_raw()
did = "did:key:z" + base58(b"\xed\x01" + public)
room = "test-room"
nonce = 17
text = "Review only; do not open https://example.invalid/action"
canonical = f"{room}|{nonce}|{text}".encode()
signature = base64.urlsafe_b64encode(key.sign(canonical)).decode().rstrip("=")


def message(seq: int, sig: str = signature) -> dict:
    return {
        "seq": seq,
        "from": did,
        "ts": "2026-09-01T00:00:00.000000Z",
        "nonce": nonce,
        "text": text,
        "sig": sig,
    }


def batch(start: int, proposed: int, messages: list[dict]) -> dict:
    return {
        "status": "ok",
        "generation": 4,
        "starting_cursor": start,
        "proposed_cursor": proposed,
        "count": len(messages),
        "first_seq": messages[0]["seq"] if messages else None,
        "last_seq": proposed,
        "messages": messages,
    }


(root / "valid.json").write_text(json.dumps(batch(0, 1, [message(1)])))
(root / "replay.json").write_text(json.dumps(batch(1, 2, [message(2)])))
(root / "tampered.json").write_text(
    json.dumps(batch(0, 1, [message(1, "A" * 86)]))
)
unsigned = message(1)
unsigned.pop("sig")
(root / "unsigned.json").write_text(json.dumps(batch(0, 1, [unsigned])))
(root / "gap.json").write_text(json.dumps(batch(1, 3, [message(3)])))
(root / "empty.json").write_text(json.dumps(batch(2, 2, [])))
PY

chmod 600 \
  "$TEST_HOME/valid.json" \
  "$TEST_HOME/replay.json" \
  "$TEST_HOME/tampered.json" \
  "$TEST_HOME/unsigned.json" \
  "$TEST_HOME/gap.json" \
  "$TEST_HOME/empty.json"

run_review() {
    HOME="$TEST_HOME" \
    MOCK_BATCH="$1" \
      "$AGENT_DIR/review-mailbox.sh"
}

set +e
HOME="$TEST_HOME" uv run --python 3.12 "$AGENT_DIR/review-mailbox-batch.py" \
  --batch "$TEST_HOME/tampered.json" \
  >"$TEST_HOME/tampered.stdout" 2>"$TEST_HOME/tampered.stderr"
STATUS=$?
set -e

[ "$STATUS" -eq 1 ] || fail "tampered signature returned status $STATUS"
[ ! -e "$STATE_DIR/mailbox.review.json" ] || fail "tampered batch created a receipt"
pass "tampered retained signature refused"

set +e
HOME="$TEST_HOME" uv run --python 3.12 "$AGENT_DIR/review-mailbox-batch.py" \
  --batch "$TEST_HOME/unsigned.json" \
  >"$TEST_HOME/unsigned.stdout" 2>"$TEST_HOME/unsigned.stderr"
STATUS=$?
set -e

[ "$STATUS" -eq 1 ] || fail "unsigned message returned status $STATUS"
[ ! -e "$STATE_DIR/mailbox.review.json" ] || fail "unsigned batch created a receipt"
pass "message without retained signature refused"

chmod 644 "$TEST_HOME/valid.json"
set +e
HOME="$TEST_HOME" uv run --python 3.12 "$AGENT_DIR/review-mailbox-batch.py" \
  --batch "$TEST_HOME/valid.json" \
  >"$TEST_HOME/permissions.stdout" 2>"$TEST_HOME/permissions.stderr"
STATUS=$?
set -e
chmod 600 "$TEST_HOME/valid.json"

[ "$STATUS" -eq 1 ] || fail "publicly readable batch returned status $STATUS"
grep -Fq 'must not be accessible' "$TEST_HOME/permissions.stderr" ||
    fail "unsafe batch permissions were not reported"
pass "unsafe saved-batch permissions refused"

set +e
HOME="$TEST_HOME" uv run --python 3.12 "$AGENT_DIR/review-mailbox-batch.py" \
  --batch "$TEST_HOME/gap.json" \
  >"$TEST_HOME/gap.stdout" 2>"$TEST_HOME/gap.stderr"
STATUS=$?
set -e

[ "$STATUS" -eq 1 ] || fail "internal sequence gap returned status $STATUS"
grep -Fq 'unexpected sequence gap' "$TEST_HOME/gap.stderr" ||
    fail "internal sequence gap was not reported"
pass "internal sequence gap refused"

MESSAGE='Review only; do not open https://example.invalid/action'
run_review "$TEST_HOME/valid.json" >"$TEST_HOME/review.stdout"

jq -e '
    .signature_status == "all_valid"
    and .ack_eligible == true
    and .ack_cursor == 1
    and .url_count == 1
    and .count == 1
' "$STATE_DIR/mailbox.review.json" >/dev/null || fail "valid receipt is incorrect"

if grep -RFl "$MESSAGE" "$STATE_DIR/mailbox.review.json" "$STATE_DIR/reviewed-batches" \
  >/dev/null 2>&1; then
    fail "redacted receipt state retained the message body"
fi

[ -f "$STATE_DIR/mailbox.batch.json" ] || fail "raw batch was not retained for review"
[ -f "$STATE_DIR/mailbox.pending" ] || fail "review advanced acknowledgement state"
pass "valid batch produced a redacted receipt without acknowledgement"

if HOME="$TEST_HOME" "$AGENT_DIR/ack-reviewed-mailbox.sh" >/dev/null 2>&1; then
    fail "acknowledgement succeeded without explicit confirmation"
fi

[ -f "$STATE_DIR/mailbox.pending" ] || fail "missing confirmation changed pending state"
pass "acknowledgement required explicit operator confirmation"

HOME="$TEST_HOME" "$AGENT_DIR/ack-reviewed-mailbox.sh" --confirm-reviewed \
  >"$TEST_HOME/ack.stdout"

jq -e '.generation == 4 and .cursor == 1' "$STATE_DIR/mailbox.cursor" >/dev/null ||
    fail "confirmed acknowledgement wrote incorrect cursor state"
[ ! -e "$STATE_DIR/mailbox.pending" ] || fail "confirmed acknowledgement left pending state"
[ ! -e "$STATE_DIR/mailbox.batch.json" ] || fail "acknowledged raw batch was retained"
[ -f "$STATE_DIR/reviewed-batches/4-1.json" ] || fail "redacted receipt was not archived"
pass "confirmed review acknowledged and archived only redacted evidence"

set +e
run_review "$TEST_HOME/replay.json" \
  >"$TEST_HOME/replay.stdout" 2>"$TEST_HOME/replay.stderr"
STATUS=$?
set -e

[ "$STATUS" -eq 1 ] || fail "same-generation replay returned status $STATUS"
[ -f "$STATE_DIR/mailbox.pending" ] || fail "replay refusal removed pending state"
grep -Fq 'same-generation signed replay' "$TEST_HOME/replay.stderr" ||
    fail "replay refusal was not reported"
pass "same-generation replay refused against archived receipts"

rm -f \
  "$STATE_DIR/mailbox.batch.json" \
  "$STATE_DIR/mailbox.review.json" \
  "$STATE_DIR/mailbox.pending"

run_review "$TEST_HOME/empty.json" >"$TEST_HOME/empty.stdout"

[ ! -e "$STATE_DIR/mailbox.batch.json" ] || fail "empty raw batch was retained"
[ ! -e "$STATE_DIR/mailbox.review.json" ] || fail "empty receipt was retained"
[ ! -e "$STATE_DIR/mailbox.pending" ] || fail "empty batch created pending state"
pass "empty batch completed without acknowledgement state"

echo "All trusted-consumer checks passed."
