#!/usr/bin/env python3
"""Network-free tests for Close Call archive verification and position modeling."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify-close-call-archive.py"
MODEL = ROOT / "scripts" / "model-close-call-position.py"
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def did() -> str:
    number = int.from_bytes(b"\xed\x01" + KEY.public_key().public_bytes_raw(), "big")
    result = ""
    while number:
        number, index = divmod(number, 58)
        result = B58[index] + result
    return "did:key:z" + result


def compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def envelope(seq: int, payload: dict) -> dict:
    room, nonce, text = "d-close1-flow", 1_800_000_000_000 + seq, compact(payload)
    signature = KEY.sign(f"{room}|{nonce}|{text}".encode())
    return {"seq": seq, "from": did(), "ts": "2026-09-30T00:00:00Z", "text": text,
            "nonce": nonce, "sig": base64.urlsafe_b64encode(signature).decode().rstrip("=")}


class ArchiveToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.flow = self.root / "flow"
        self.flow.mkdir()
        self.records = self.root / "records"
        self.records.mkdir()
        full = compact({"input": {"n": 1}, "output": {"sweep": 1, "minted": [did()]}}).encode()
        redacted = compact({"input": {"n": 2, "trades": [{"redacted": "private room"}]},
                            "output": {"sweep": 2, "minted": []}}).encode()
        full_hash = hashlib.sha256(full).hexdigest()
        original_hash = "2" * 64
        redacted_hash = hashlib.sha256(redacted).hexdigest()
        self.entries = [
            {"bytes": len(full), "file": full_hash, "n": 1,
             "path": f"sweeps/{full_hash}.json", "status": "full"},
            {"bytes": len(redacted), "file": original_hash, "n": 2,
             "path": f"redacted/{original_hash}.json", "redacted": 1,
             "sha256": redacted_hash, "status": "redacted"},
        ]
        self.index = self.root / "index.json"
        self.index.write_text(compact({"contest": "close-1", "sweeps": self.entries}))
        self.full = self.records / "one.json"
        self.redacted = self.records / "two.json"
        self.full.write_bytes(full)
        self.redacted.write_bytes(redacted)
        for n, commitment in ((1, full_hash), (2, original_hash)):
            payload = {"t": "flow", "n": n, "file": commitment}
            (self.flow / f"{n:016d}.json").write_text(compact(envelope(n, payload)) + "\n")

    def tearDown(self):
        self.temp.cleanup()

    def command(self):
        return [sys.executable, str(VERIFY), "--index", str(self.index),
                "--signed-flow-directory", str(self.flow), "--contest-id", "close-1",
                "--record", f"1={self.full}", "--record", f"2={self.redacted}"]

    def test_full_and_redacted_records_pass_with_explicit_limits(self):
        result = subprocess.run(self.command(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["signed_commitments_verified"], 2)
        self.assertEqual((report["full_records"], report["redacted_records"]), (1, 1))
        self.assertFalse(report["network_access"])

    def test_index_commitment_and_record_tampering_fail(self):
        index = json.loads(self.index.read_text())
        index["sweeps"][0]["file"] = "3" * 64
        index["sweeps"][0]["path"] = f"sweeps/{'3' * 64}.json"
        self.index.write_text(compact(index))
        result = subprocess.run(self.command(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("ERROR:"), result.stderr)

        self.setUp_fresh()
        self.full.write_bytes(self.full.read_bytes() + b" ")
        result = subprocess.run(self.command(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def setUp_fresh(self):
        self.tearDown()
        self.setUp()

    def test_model_matches_fold_fee_and_score_math(self):
        command = [sys.executable, str(MODEL), "--side", "buy", "--quantity", "10",
                   "--entry-price", "228", "--sweep-close", "230", "--reference", "228",
                   "--settlement-price", "220", "--settlement-price", "240"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["maker_fee"], "22.80")
        self.assertEqual(report["break_even_settlement_price"], "230.28")
        self.assertEqual(report["scenarios"][1]["score_after_fee"], "97.20")
        self.assertTrue(report["within_five_percent_limit"])

    def test_model_refuses_unsafe_amounts_and_excess_cash(self):
        base = [sys.executable, str(MODEL), "--side", "sell", "--quantity", "0.01",
                "--entry-price", "228", "--sweep-close", "228", "--settlement-price", "220"]
        self.assertEqual(subprocess.run(base, capture_output=True).returncode, 1)
        base[base.index("0.01")] = "100"
        self.assertEqual(subprocess.run(base, capture_output=True).returncode, 1)

    def test_tools_have_no_network_or_process_imports(self):
        for path in (VERIFY, MODEL):
            tree = ast.parse(path.read_text())
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertTrue({"socket", "urllib", "requests", "httpx", "subprocess"}.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()
