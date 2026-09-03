#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}"
TEST_HOME="$(mktemp -d)"
AGENT_DIR="$TEST_HOME/technocore-agent"
STATE_DIR="$TEST_HOME/flop"
trap 'find "$TEST_HOME" -depth -delete' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

mkdir -p "$AGENT_DIR" "$STATE_DIR"
chmod 700 "$TEST_HOME" "$AGENT_DIR" "$STATE_DIR"
install -m 700 "$ROOT_DIR/scripts/review-tclk-batch.sh" "$AGENT_DIR/review-tclk-batch.sh"
install -m 700 "$ROOT_DIR/scripts/validate-tclk-transcript.py" "$AGENT_DIR/validate-tclk-transcript.py"
install -m 600 "$ROOT_DIR/requirements/verifier.txt" "$AGENT_DIR/requirements-verifier.txt"
printf '%s\n' tclk-wrapper-test >"$STATE_DIR/mailbox.txt"
chmod 600 "$STATE_DIR/mailbox.txt"

UV_OFFLINE=1 uv run --python 3.12 \
  --with-requirements "$ROOT_DIR/requirements/verifier.txt" \
  python - "$STATE_DIR" <<'PY'
import base64, hashlib, json, sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

state=Path(sys.argv[1]); room="tclk-wrapper-test"
alphabet="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
key=Ed25519PrivateKey.generate(); raw=b"\xed\x01"+key.public_key().public_bytes_raw()
n=int.from_bytes(raw,"big"); encoded=""
while n: n,r=divmod(n,58); encoded=alphabet[r]+encoded
did="did:key:z"+("1"*(len(raw)-len(raw.lstrip(b"\0"))))+encoded
canonical=lambda v:json.dumps(v,ensure_ascii=True,sort_keys=True,separators=(",",":"))
fields={"type":"offer","from":did,"role":"payer","amount":"1","asset":"TEST",
        "lock":"hash","rails":["paper"],"claimByMs":4102444740000,
        "refundAfterMs":4102444800000,"expiresMs":4102444680000,"nonce":"01234567"}
material="FLOP::tclk::v1|offer|"+canonical(fields)
frame={**fields,"id":"0x"+hashlib.sha256(material.encode()).hexdigest()}
text="tclk1 "+canonical(frame); nonce=101
sig=base64.urlsafe_b64encode(key.sign(f"{room}|{nonce}|{text}".encode())).decode().rstrip("=")
message={"seq":1,"from":did,"ts":"2099-12-31T23:50:00Z","nonce":nonce,"text":text,"sig":sig}
batch={"status":"ok","generation":13,"starting_cursor":0,"proposed_cursor":1,
       "count":1,"first_seq":1,"last_seq":1,"messages":[message]}
receipt={"schema_version":1,"generation":13,"starting_cursor":0,"proposed_cursor":1,
         "count":1,"batch_sha256":"0"*64,"signature_status":"all_valid",
         "ack_eligible":True,"ack_cursor":1,"url_count":0,"messages":[]}
(state/"mailbox.batch.json").write_text(json.dumps(batch))
(state/"mailbox.review.json").write_text(json.dumps(receipt))
PY
chmod 600 "$STATE_DIR/mailbox.batch.json" "$STATE_DIR/mailbox.review.json"

HOME="$TEST_HOME" UV_CACHE_DIR="$TEST_UV_CACHE_DIR" UV_OFFLINE=1 \
  "$AGENT_DIR/review-tclk-batch.sh" >"$TEST_HOME/out"
jq -e '.schema_version == 2 and .generation == 13 and
       .starting_cursor == 0 and .proposed_cursor == 1 and
       .first_seq == 1 and .last_seq == 1 and .side_effects == false' \
  "$STATE_DIR/tclk.review.json" >/dev/null || fail "wrapper wrote an invalid report"
[ "$(stat -c '%a' "$STATE_DIR/tclk.review.json")" = 600 ] || fail "report mode is not 600"
[ -f "$STATE_DIR/mailbox.batch.json" ] || fail "wrapper removed the saved batch"
[ ! -e "$STATE_DIR/mailbox.cursor" ] || fail "wrapper advanced the mailbox cursor"
pass "matching reviewed batch produced a private state-bound report"

jq '.generation=14' "$STATE_DIR/mailbox.review.json" >"$TEST_HOME/bad-review"
install -m 600 "$TEST_HOME/bad-review" "$STATE_DIR/mailbox.review.json"
BEFORE="$(sha256sum "$STATE_DIR/tclk.review.json")"
if HOME="$TEST_HOME" UV_CACHE_DIR="$TEST_UV_CACHE_DIR" UV_OFFLINE=1 \
  "$AGENT_DIR/review-tclk-batch.sh" >/dev/null 2>&1; then
    fail "mismatched generic review receipt was accepted"
fi
[ "$(sha256sum "$STATE_DIR/tclk.review.json")" = "$BEFORE" ] ||
    fail "failed review replaced the earlier report"
pass "mismatched trusted review receipt failed without replacing evidence"

if grep -En 'curl|send\.sh|ack-mailbox|ack-reviewed|https?://' \
  "$ROOT_DIR/scripts/review-tclk-batch.sh" >/dev/null; then
    fail "wrapper contains a network, sender, or acknowledgement path"
fi
pass "wrapper has no network, sender, or acknowledgement path"

echo "All manual tclk review-wrapper checks passed."
