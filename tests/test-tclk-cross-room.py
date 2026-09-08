#!/usr/bin/env python3
"""Exercise real signatures across independently captured board/deal exports."""
import base64
import copy
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(ROOT / "tests/test-tclk-parser-properties.py"))
frames = fixture["frames"]()
contract = frames[1][0]["contract"]
rooms = {"board": "tclk-offers", "deal": "mb-p-tclk-" + contract[2:18]}
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    records = {"board": [], "deal": []}
    for index, (frame, key, timestamp) in enumerate(frames):
        side = "board" if index < 2 else "deal"
        seq = len(records[side]) + 1
        text = "tclk1 " + fixture["canonical"](frame)
        nonce = 1000 + index
        sig = base64.urlsafe_b64encode(key.sign(f"{rooms[side]}|{nonce}|{text}".encode())).decode().rstrip("=")
        records[side].append({"seq": seq, "from": frame["from"], "ts": timestamp,
                              "nonce": nonce, "text": text, "sig": sig})
    capture = {}
    for side in records:
        raw = ("\n".join(json.dumps(row) for row in records[side]) + "\n").encode()
        (root / side).write_bytes(raw)
        capture[side] = {"room": rooms[side], "generation": 7 if side == "board" else 19,
                         "first_seq": 1, "last_seq": len(records[side]),
                         "sha256": hashlib.sha256(raw).hexdigest()}
    command = [sys.executable, str(ROOT / "scripts/audit-tclk-cross-room.py"),
               "--board", str(root / "board"), "--deal", str(root / "deal"),
               "--capture", str(root / "capture"), "--contract", contract]

    def run(metadata):
        (root / "capture").write_text(json.dumps(metadata))
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert before == {p.name: p.read_bytes() for p in root.iterdir()}
        return result

    good = run(capture)
    assert good.returncode == 0, good.stderr
    report = json.loads(good.stdout)
    assert report["status"] == "claimed"
    assert report["captures"]["board"]["generation"] == 7
    assert report["captures"]["deal"]["generation"] == 19
    assert not report["venue_metadata_authenticated"] and not report["side_effects"]
    changed = copy.deepcopy(capture)
    changed["deal"]["generation"] = 20
    assert json.loads(run(changed).stdout)["binding_sha256"] != report["binding_sha256"]
    for field, value in (("room", "wrong-room"), ("last_seq", 4), ("sha256", "0" * 64)):
        bad = copy.deepcopy(capture)
        bad["deal"][field] = value
        result = run(bad)
        assert result.returncode == 1 and not result.stdout and "Traceback" not in result.stderr
    original = (root / "deal").read_bytes()
    for rows in (records["deal"][::-1], records["deal"][::2],
                 [*records["deal"], records["deal"][-1]],
                 [{**records["deal"][0], "sig": "A" * 86}, *records["deal"][1:]]):
        raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        (root / "deal").write_bytes(raw)
        bad = copy.deepcopy(capture)
        bad["deal"]["sha256"] = hashlib.sha256(raw).hexdigest()
        result = run(bad)
        assert result.returncode == 1 and not result.stdout
    (root / "deal").write_bytes(original)
print("PASS: cross-room claim verified with independent generation and byte bindings")
print("PASS: wrong room, altered digest, truncation, gaps, replay and signatures rejected")
