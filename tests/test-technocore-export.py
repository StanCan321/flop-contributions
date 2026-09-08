#!/usr/bin/env python3
"""Network-free checks for the byte-exact Technocore export verifier."""
import base64, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1]; TOOL=ROOT/"scripts/verify-technocore-export.py"; ROOM="export-test"
ALPHABET="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
key=Ed25519PrivateKey.from_private_bytes(bytes(range(32))); raw=b"\xed\x01"+key.public_key().public_bytes_raw(); n=int.from_bytes(raw,"big"); enc=""
while n: n,r=divmod(n,58); enc=ALPHABET[r]+enc
did="did:key:z"+enc
def signed(seq,text):
    nonce=8000+seq; sig=base64.urlsafe_b64encode(key.sign(f"{ROOM}|{nonce}|{text}".encode())).decode().rstrip("=")
    return {"seq":seq,"from":did,"ts":"2026-09-08T00:00:00Z","text":text,"nonce":nonce,"sig":sig}
records=[{"seq":4,"from":"anon","ts":"2026-09-08T00:00:00Z","text":"data"},signed(5,"signed data")]
def run(lines):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"export.jsonl"; path.write_text("\n".join(json.dumps(x,separators=(",",":")) if not isinstance(x,str) else x for x in lines)+"\n")
        before=hashlib.sha256(path.read_bytes()).digest(); result=subprocess.run([sys.executable,str(TOOL),"--room",ROOM,"--generation","13",str(path)],capture_output=True,text=True)
        assert hashlib.sha256(path.read_bytes()).digest()==before and list(Path(directory).iterdir())==[path]
        return result
ok=run(records); assert ok.returncode==0 and json.loads(ok.stdout)["signed_count"]==1
for bad in ([records[1],records[0]],[records[0],{**records[1],"seq":6}],[records[0],{**records[1],"sig":"A"*86}],[records[0],'{"seq":5,"seq":5}']):
    result=run(bad); assert result.returncode==1 and result.stdout=="" and result.stderr.startswith("ERROR:")
print("PASS: complete mixed export verified with redacted output")
print("PASS: reorder, gap, signature alteration, and duplicate keys failed without state change")
print("All Technocore export-verification checks passed.")
