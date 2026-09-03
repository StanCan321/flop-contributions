#!/usr/bin/env python3
"""Deterministic adversarial properties for the read-only tclk parser."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-tclk-transcript.py"
ROOM = "property-test"
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(tag: str, value: object) -> str:
    material = f"FLOP::tclk::v1|{tag}|{canonical(value)}".encode("ascii")
    return "0x" + hashlib.sha256(material).hexdigest()


def did_for(key: Ed25519PrivateKey) -> str:
    raw = b"\xed\x01" + key.public_key().public_bytes_raw()
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "did:key:z" + "1" * (len(raw) - len(raw.lstrip(b"\0"))) + encoded


PAYER_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PAYEE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
PAYER = did_for(PAYER_KEY)
PAYEE = did_for(PAYEE_KEY)


def signed_message(seq: int, frame: dict, key: Ed25519PrivateKey, timestamp: str) -> dict:
    text = "tclk1 " + canonical(frame)
    nonce = 1_000 + seq
    signature = key.sign(f"{ROOM}|{nonce}|{text}".encode())
    return {
        "seq": seq,
        "from": frame["from"],
        "ts": timestamp,
        "nonce": nonce,
        "text": text,
        "sig": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def frames() -> list[tuple[dict, Ed25519PrivateKey, str]]:
    secret = bytes.fromhex("42" * 32)
    statement = "0x" + hashlib.sha256(secret).hexdigest()
    offer_fields = {
        "type": "offer", "from": PAYER, "role": "payer", "amount": "1",
        "asset": "TEST", "lock": "hash", "rails": ["paper"],
        "claimByMs": 4_102_444_740_000, "refundAfterMs": 4_102_444_800_000,
        "expiresMs": 4_102_444_680_000, "nonce": "01234567",
    }
    offer = {**offer_fields, "id": digest("offer", offer_fields)}
    accept_core = {
        "from": PAYEE, "ref": offer["id"], "statement": statement,
        "nonce": "89abcdef",
    }
    contract = digest("contract", {"offer": offer, "accept": accept_core})
    accept = {"type": "accept", **accept_core, "contract": contract}
    return [
        (offer, PAYER_KEY, "2099-12-31T23:50:00Z"),
        (accept, PAYEE_KEY, "2099-12-31T23:51:00Z"),
        ({"type": "lock", "from": PAYER, "contract": contract,
          "rail": "paper", "ref": "local"}, PAYER_KEY, "2099-12-31T23:52:00Z"),
        ({"type": "reveal", "from": PAYEE, "contract": contract,
          "secret": "0x" + secret.hex()}, PAYEE_KEY, "2099-12-31T23:53:00Z"),
        ({"type": "receipt", "from": PAYER, "contract": contract,
          "outcome": "claimed", "rail": "paper", "ref": "local"},
         PAYER_KEY, "2099-12-31T23:54:00Z"),
    ]


def batch(messages: list[dict]) -> dict:
    return {
        "status": "ok", "generation": 9, "starting_cursor": 0,
        "proposed_cursor": len(messages), "count": len(messages),
        "first_seq": 1 if messages else None, "last_seq": len(messages),
        "messages": messages,
    }


def signed_batch() -> dict:
    return batch([
        signed_message(index, frame, key, timestamp)
        for index, (frame, key, timestamp) in enumerate(frames(), 1)
    ])


def assert_clean_rejection(name: str, raw: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "batch.json"
        path.write_text(raw, encoding="utf-8")
        before = hashlib.sha256(path.read_bytes()).digest()
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--room", ROOM, str(path)],
            text=True, capture_output=True, timeout=5, check=False,
        )
        assert result.returncode == 1, (name, result.returncode, result.stderr)
        assert result.stdout == "", (name, result.stdout)
        assert result.stderr.startswith("ERROR: "), (name, result.stderr)
        assert hashlib.sha256(path.read_bytes()).digest() == before, name
        assert sorted(item.name for item in Path(directory).iterdir()) == ["batch.json"], name


cases: list[tuple[str, str]] = [
    ("malformed JSON", '{"status":"ok"'),
    ("duplicate JSON key", canonical(signed_batch()).replace(
        '"status":"ok"', '"status":"ok","status":"ok"', 1)),
]

for name, mutate in (
    ("unknown batch field", lambda value: value.update(extra=True)),
    ("unsafe generation", lambda value: value.update(generation=9_007_199_254_740_992)),
    ("unsafe sequence", lambda value: value["messages"][0].update(seq=9_007_199_254_740_992)),
    ("very large transport nonce", lambda value: value["messages"][0].update(nonce=10**20)),
    ("unknown message field", lambda value: value["messages"][0].update(extra=True)),
):
    candidate = signed_batch()
    mutate(candidate)
    cases.append((name, canonical(candidate)))

for timestamp in ("not-a-time", "2026-01-01T00:00:00", "999999-01-01T00:00:00Z"):
    candidate = signed_batch()
    frame, key, _ = frames()[0]
    candidate["messages"][0] = signed_message(1, frame, key, timestamp)
    cases.append((f"invalid timestamp {timestamp}", canonical(candidate)))

for label, frame_mutation in (
    ("Unicode edge", lambda frame: frame.update(asset="TE\u200bST")),
    ("unknown frame field", lambda frame: frame.update(extra="x")),
    ("unsafe deadline", lambda frame: frame.update(claimByMs=9_007_199_254_740_992)),
    ("very large frame nonce", lambda frame: frame.update(nonce="f" * 65)),
):
    candidate = signed_batch()
    frame, key, timestamp = frames()[0]
    frame_mutation(frame)
    candidate["messages"][0] = signed_message(1, frame, key, timestamp)
    cases.append((label, canonical(candidate)))

rng = random.Random(0xF10F)
valid_frames = frames()
orders: set[tuple[int, ...]] = set()
while len(orders) < 24:
    order = list(range(len(valid_frames)))
    rng.shuffle(order)
    if order != list(range(len(valid_frames))):
        orders.add(tuple(order))
for order in sorted(orders):
    messages = [
        signed_message(seq, *valid_frames[index])
        for seq, index in enumerate(order, 1)
    ]
    cases.append((f"transition permutation {order}", canonical(batch(messages))))

for case_name, case_raw in cases:
    assert_clean_rejection(case_name, case_raw)

print(f"PASS: {len(cases)} malformed and randomized cases failed cleanly without state change")
print("All tclk parser property checks passed.")
