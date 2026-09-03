#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'find "$TEST_DIR" -depth -delete' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

uv run --python 3.12 \
  --with-requirements "$ROOT_DIR/requirements/verifier.txt" \
  python - "$TEST_DIR" <<'PY'
import base64, hashlib, json, sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

root = Path(sys.argv[1])
alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(raw):
    n=int.from_bytes(raw,"big"); out=""
    while n: n,r=divmod(n,58); out=alphabet[r]+out
    return "1"*(len(raw)-len(raw.lstrip(b"\0")))+out
keys=[Ed25519PrivateKey.generate(),Ed25519PrivateKey.generate()]
def did(key): return "did:key:z"+b58(b"\xed\x01"+key.public_key().public_bytes_raw())
payer,payee=map(did,keys)
domain = "FLOP::tclk::v1"

def canonical(v): return json.dumps(v, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
def digest(tag, v): return "0x" + hashlib.sha256(f"{domain}|{tag}|{canonical(v)}".encode()).hexdigest()
def line(v): return "tclk1 " + canonical(v)
room="tclk-test"
def msg(seq, sender, frame, ts):
    text=line(frame); nonce=100+seq; key=keys[0] if sender==payer else keys[1]
    sig=base64.urlsafe_b64encode(key.sign(f"{room}|{nonce}|{text}".encode())).decode().rstrip("=")
    return {"seq":seq,"from":sender,"ts":ts,"nonce":nonce,"text":text,"sig":sig}
def batch(messages, start=0):
    last=messages[-1]["seq"] if messages else start
    return {"status":"ok","generation":7,"starting_cursor":start,
            "proposed_cursor":last,"count":len(messages),
            "first_seq":messages[0]["seq"] if messages else None,
            "last_seq":last,"messages":messages}
def save(name, messages, start=0): (root / name).write_text(json.dumps(batch(messages,start)))
def resign(m):
    key=keys[0] if m["from"]==payer else keys[1]
    m["sig"]=base64.urlsafe_b64encode(key.sign(f'{room}|{m["nonce"]}|{m["text"]}'.encode())).decode().rstrip("=")

offer = {"type":"offer","from":payer,"role":"payer","amount":"1","asset":"FLOP",
         "lock":"hash","rails":["paper"],"claimByMs":4102444740000,
         "refundAfterMs":4102444800000,"expiresMs":4102444680000,"nonce":"01234567"}
offer["id"] = digest("offer", offer)
secret = "0x" + "42" * 32
statement = "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
core = {"from":payee,"ref":offer["id"],"statement":statement,"nonce":"89abcdef"}
accept = {"type":"accept",**core,"contract":digest("contract", {"offer":offer,"accept":core})}
lock = {"type":"lock","from":payer,"contract":accept["contract"],"rail":"paper","ref":"test-lock"}
reveal = {"type":"reveal","from":payee,"contract":accept["contract"],"secret":secret}
receipt = {"type":"receipt","from":payer,"contract":accept["contract"],"outcome":"claimed"}
times = ["2099-12-31T23:50:00Z","2099-12-31T23:51:00Z","2099-12-31T23:52:00Z",
         "2099-12-31T23:53:00Z","2099-12-31T23:54:00Z"]
valid = [msg(i+1, f["from"], f, times[i]) for i, f in enumerate([offer,accept,lock,reveal,receipt])]
instruction=f"touch {root / 'message-was-executed'}; https://example.invalid/act"
ordinary=msg(6,payer,offer,times[-1]); ordinary["text"]=instruction
ordinary["sig"]=base64.urlsafe_b64encode(keys[0].sign(f"{room}|106|{instruction}".encode())).decode().rstrip("=")
save("valid.json",valid+[ordinary])

def variant(name, index, change):
    rows = json.loads(json.dumps(valid)); change(rows[index]); resign(rows[index]); save(name, rows)

variant("did-mismatch.json", 1, lambda m: m.update({"from":payer}))
unsigned=json.loads(json.dumps(valid)); unsigned[0].pop("sig"); save("unsigned.json",unsigned)
tampered=json.loads(json.dumps(valid)); tampered[0]["text"] += " "; save("tampered-signature.json",tampered)
variant("unknown.json", 0, lambda m: m.update(text=m["text"][:-1]+',"surprise":true}'))
variant("noncanonical.json", 0, lambda m: m.update(text="tclk1 "+json.dumps(offer)))
variant("wrong-secret.json", 3, lambda m: m.update(text=line({**reveal,"secret":"0x"+"00"*32})))
early = json.loads(json.dumps(valid)); early[2] = msg(3,payee,reveal,times[2]); save("reveal-before-lock.json",early)
expired=json.loads(json.dumps(valid)); expired[1]["ts"]="2100-01-01T00:00:01Z"; save("expired-accept.json",expired)
refund={"type":"refund","from":payer,"contract":accept["contract"]}
early_refund=json.loads(json.dumps(valid)); early_refund[3]=msg(4,payer,refund,times[3]); save("early-refund.json",early_refund)
wrong_party=json.loads(json.dumps(valid)); wrong_party[2]=msg(3,payee,{**lock,"from":payee},times[2]); save("wrong-party.json",wrong_party)
save("truncated.json",valid[1:])
duplicate = valid[:1] + valid[:1]; save("replay.json", duplicate)
point = json.loads(json.dumps(offer)); point["lock"]="point"; point["id"]=digest("offer",{k:v for k,v in point.items() if k!="id"})
save("point.json", [msg(1,payer,point,times[0])])
PY

run_ok() {
    uv run --python 3.12 --with-requirements "$ROOT_DIR/requirements/verifier.txt" \
      "$ROOT_DIR/scripts/validate-tclk-transcript.py" --room tclk-test "$TEST_DIR/$1"
}

run_bad() {
    if run_ok "$1" >"$TEST_DIR/out" 2>"$TEST_DIR/err"; then
        fail "$1 was accepted"
    fi
}

run_ok valid.json >"$TEST_DIR/result.json"
jq -e '.accepted_frame_count == 5 and .ignored_non_tclk_count == 1 and
       .contracts[0].status == "claimed" and .side_effects == false and
       .schema_version == 2 and .generation == 7 and
       .starting_cursor == 0 and .proposed_cursor == 6 and
       .first_seq == 1 and .last_seq == 6 and
       (.batch_binding_sha256 | test("^[0-9a-f]{64}$"))' \
  "$TEST_DIR/result.json" >/dev/null || fail "valid transcript summary is incorrect"
if grep -Fq "0x$(printf '42%.0s' {1..32})" "$TEST_DIR/result.json"; then
    fail "redacted output retained the revealed secret"
fi
pass "valid hash-lock transcript accepted with redacted output"
[ ! -e "$TEST_DIR/message-was-executed" ] || fail "instruction-like text was executed"
pass "instruction-like text and URL remained inert"

for fixture in unsigned tampered-signature did-mismatch unknown noncanonical wrong-secret \
  reveal-before-lock expired-accept early-refund wrong-party truncated replay point; do
    run_bad "$fixture.json"
    pass "$fixture transcript rejected"
done

if rg -n 'subprocess|requests|urllib|socket|https?://|os\.system|eval\(|exec\(' \
  "$ROOT_DIR/scripts/validate-tclk-transcript.py" >/dev/null; then
    fail "validator contains a network or execution primitive"
fi
pass "validator has no network, subprocess, URL, or code-execution primitive"

echo "All read-only tclk transcript checks passed."
