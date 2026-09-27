#!/usr/bin/env python3
"""Network-free hostile-input tests for the Close Call verifier."""

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
TOOL = ROOT / "scripts" / "verify-close-call.py"
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ROOMS = [
    "d-close1-flow", "d-close1-state", "d-close1-price",
    "d-close1-positions", "d-close1-pnl",
]


def did() -> str:
    raw = b"\xed\x01" + KEY.public_key().public_bytes_raw()
    number, result = int.from_bytes(raw, "big"), ""
    while number:
        number, index = divmod(number, 58)
        result = B58[index] + result
    return "did:key:z" + result


def canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def envelope(room: str, seq: int, message: object) -> dict:
    text = canonical(message)
    nonce = 1_790_000_000_000 + seq
    signature = KEY.sign(f"{room}|{nonce}|{text}".encode())
    return {
        "seq": seq, "from": did(), "ts": "2026-09-25T12:00:00Z", "text": text,
        "nonce": nonce, "sig": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


class CloseCallVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.package.mkdir()
        contest = {
            "contest_id": "close-1",
            "rooms": {"referee": ROOMS},
        }
        artifacts = {
            "contest.json": canonical(contest).encode(),
            "rules.txt": b"synthetic frozen rules\n",
        }
        for name, raw in artifacts.items():
            (self.package / name).write_bytes(raw)
        manifest = {
            "schema_version": 1,
            "package": "technocore-close-call",
            "entrypoint": "rules.txt",
            "files": {
                name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "url": name}
                for name, raw in artifacts.items()
            },
        }
        manifest_raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
        (self.package / "manifest.json").write_bytes(manifest_raw)
        self.manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
        file_hashes = {1: "1" * 64, 2: "2" * 64}
        self.records = {}
        for room in ROOMS:
            kind = room.rsplit("-", 1)[1]
            rows = []
            if kind == "price":
                rows.append(envelope(room, 1, {
                    "t": "seed", "season": "close-1", "package": self.manifest_hash,
                    "rooms": ROOMS, "price": "100.00",
                }))
                rows.extend(envelope(room, n + 1, {"t": "price", "n": n, "file": file_hashes[n]})
                            for n in (1, 2))
            else:
                rows.extend(envelope(room, n, {"t": kind, "n": n, "file": file_hashes[n]})
                            for n in (1, 2))
            self.records[room] = rows
        self.exports = self.root / "exports"
        self.exports.mkdir()
        self.write_exports()

    def tearDown(self):
        self.temp.cleanup()

    def write_exports(self):
        for room, rows in self.records.items():
            raw = b"".join(canonical(row).encode() + b"\n" for row in rows)
            (self.exports / f"{room}.jsonl").write_bytes(raw)

    def command(self):
        command = [
            sys.executable, str(TOOL), "--package", str(self.package),
            "--expected-manifest-sha256", self.manifest_hash,
            "--contest-id", "close-1",
        ]
        for room in ROOMS:
            command.extend(["--room-export", f"{room}={self.exports / f'{room}.jsonl'}"])
        return command

    def invoke(self):
        inputs = [p for p in self.root.rglob("*") if p.is_file()]
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in inputs}
        result = subprocess.run(self.command(), capture_output=True, text=True)
        after = {p: hashlib.sha256(p.read_bytes()).digest() for p in inputs}
        self.assertEqual(before, after)
        return result

    def assert_refused(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("ERROR:"), result.stderr)

    def test_complete_signed_package_and_sweeps_pass(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["latest_sweep"], 2)
        self.assertFalse(report["network_access"])
        self.assertFalse(report["side_effects"])
        self.assertNotIn(did(), result.stdout)

    def test_manifest_hash_and_artifact_drift_fail(self):
        self.manifest_hash = "0" * 64
        self.assert_refused()
        self.manifest_hash = hashlib.sha256((self.package / "manifest.json").read_bytes()).hexdigest()
        (self.package / "rules.txt").write_text("changed")
        self.assert_refused()

    def test_tampered_signature_and_duplicate_inner_key_fail(self):
        self.records["d-close1-flow"][0]["sig"] = "A" * 86
        self.write_exports()
        self.assert_refused()
        self.setUp_fresh_records()
        row = self.records["d-close1-flow"][0]
        row["text"] = '{"t":"flow","t":"flow","n":1,"file":"' + "1" * 64 + '"}'
        row["sig"] = base64.urlsafe_b64encode(
            KEY.sign(f"d-close1-flow|{row['nonce']}|{row['text']}".encode())
        ).decode().rstrip("=")
        self.write_exports()
        self.assert_refused()

    def setUp_fresh_records(self):
        self.tearDown()
        self.setUp()

    def test_sequence_gap_and_cross_room_commitment_mismatch_fail(self):
        self.records["d-close1-state"][1]["seq"] = 3
        self.write_exports()
        self.assert_refused()
        self.setUp_fresh_records()
        message = {"t": "pnl", "n": 2, "file": "3" * 64}
        self.records["d-close1-pnl"][1] = envelope("d-close1-pnl", 2, message)
        self.write_exports()
        self.assert_refused()

    def test_wrong_seed_binding_and_post_final_message_fail(self):
        seed = self.records["d-close1-price"][0]
        bad = {"t": "seed", "season": "other", "package": self.manifest_hash, "rooms": ROOMS}
        self.records["d-close1-price"][0] = envelope("d-close1-price", 1, bad)
        self.write_exports()
        self.assert_refused()
        self.setUp_fresh_records()
        final = envelope("d-close1-price", 4, {"t": "final", "season": "close-1", "price": "101"})
        later = envelope("d-close1-price", 5, {"t": "price", "n": 3, "file": "3" * 64})
        self.records["d-close1-price"].extend([final, later])
        self.write_exports()
        self.assert_refused()

    def test_missing_export_fails(self):
        self.command = lambda: [
            sys.executable, str(TOOL), "--package", str(self.package),
            "--expected-manifest-sha256", self.manifest_hash, "--contest-id", "close-1",
            *sum((["--room-export", f"{room}={self.exports / f'{room}.jsonl'}"]
                  for room in ROOMS[:-1]), []),
        ]
        self.assert_refused()

    def test_duplicate_export_fails(self):
        command = self.command()
        command.extend(["--room-export", f"{ROOMS[0]}={self.exports / f'{ROOMS[0]}.jsonl'}"])
        self.command = lambda: command
        self.assert_refused()

    def test_symlink_export_and_escaping_artifact_fail(self):
        original = self.exports / f"{ROOMS[0]}.jsonl"
        linked = self.root / "linked-export.jsonl"
        linked.symlink_to(original)
        command = self.command()
        export_index = command.index(f"{ROOMS[0]}={original}")
        command[export_index] = f"{ROOMS[0]}={linked}"
        self.command = lambda: command
        self.assert_refused()

        self.setUp_fresh_records()
        outside = self.root / "outside.txt"
        outside.write_text("outside\n")
        link = self.package / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        manifest_path = self.package / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        raw = outside.read_bytes()
        manifest["files"]["linked/outside.txt"] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "url": "linked/outside.txt",
        }
        manifest_raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
        manifest_path.write_bytes(manifest_raw)
        self.manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
        seed = self.records["d-close1-price"][0]
        seed_message = json.loads(seed["text"])
        seed_message["package"] = self.manifest_hash
        self.records["d-close1-price"][0] = envelope("d-close1-price", 1, seed_message)
        self.write_exports()
        self.assert_refused()

    def test_implementation_has_no_network_or_process_surface(self):
        tree = ast.parse(TOOL.read_text())
        imports = {alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])}
        self.assertTrue({"socket", "urllib", "requests", "httpx", "subprocess"}.isdisjoint(imports))
        source = TOOL.read_text()
        for forbidden in ("urlopen(", "requests.", "subprocess.", "os.system(", "SIGN_SEED"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
