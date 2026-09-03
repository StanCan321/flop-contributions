#!/usr/bin/env python3
"""Zero-value, network-free PaperRail claim and refund lifecycle rehearsal."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate-tclk-transcript.py"
SPEC = importlib.util.spec_from_file_location("tclk_validator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

ROOM = "tclk-paper-local"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = B58[remainder] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + encoded


def did(key: Ed25519PrivateKey) -> str:
    public = key.public_key().public_bytes_raw()
    return "did:key:z" + base58(b"\xed\x01" + public)


@dataclass
class LocalPaperRail:
    """A single-contract note with compare-and-set-like guarded transitions."""

    statement: str
    refund_after_ms: int
    status: str = "locked"
    secret: str | None = None

    def claim(self, supplied: str, now_ms: int) -> None:
        if self.status != "locked" or now_ms >= self.refund_after_ms:
            raise ValueError("claim is unavailable")
        opened = "0x" + hashlib.sha256(bytes.fromhex(supplied[2:])).hexdigest()
        if opened != self.statement:
            raise ValueError("secret does not open statement")
        self.status, self.secret = "claimed", supplied

    def refund(self, now_ms: int) -> None:
        if self.status != "locked" or now_ms < self.refund_after_ms:
            raise ValueError("refund is unavailable")
        self.status = "refunded"


def signed_message(seq: int, key: Ed25519PrivateKey, sender: str, frame: dict, timestamp: str) -> dict:
    text = validator.PREFIX + validator.canonical(frame)
    nonce = 10_000 + seq
    canonical_envelope = f"{ROOM}|{nonce}|{text}".encode()
    signature = base64.urlsafe_b64encode(key.sign(canonical_envelope)).decode().rstrip("=")
    return {"seq": seq, "from": sender, "ts": timestamp, "nonce": nonce, "text": text, "sig": signature}


def lifecycle(refund: bool) -> tuple[dict, LocalPaperRail, str]:
    payer_key, payee_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    payer, payee = did(payer_key), did(payee_key)
    secret = "0x" + "51" * 32
    statement = "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()
    offer_fields = {
        "type": "offer", "from": payer, "role": "payer", "amount": "1",
        "asset": "TEST", "lock": "hash", "rails": ["paper"],
        "claimByMs": 4_102_444_740_000, "refundAfterMs": 4_102_444_800_000,
        "expiresMs": 4_102_444_680_000, "nonce": "01234567",
    }
    offer = {**offer_fields, "id": validator.digest("offer", offer_fields)}
    accept_core = {"from": payee, "ref": offer["id"], "statement": statement, "nonce": "89abcdef"}
    accept = {"type": "accept", **accept_core,
              "contract": validator.digest("contract", {"offer": offer, "accept": accept_core})}
    lock = {"type": "lock", "from": payer, "contract": accept["contract"],
            "rail": "paper", "ref": "local-note"}
    rail = LocalPaperRail(statement, offer["refundAfterMs"])
    frames = [offer, accept, lock]
    keys = [payer_key, payee_key, payer_key]
    senders = [payer, payee, payer]
    times = ["2099-12-31T23:50:00Z", "2099-12-31T23:51:00Z", "2099-12-31T23:52:00Z"]

    if refund:
        rail.refund(offer["refundAfterMs"])
        terminal = {"type": "refund", "from": payer, "contract": accept["contract"]}
        receipt = {"type": "receipt", "from": payee, "contract": accept["contract"], "outcome": "refunded"}
        frames += [terminal, receipt]
        keys += [payer_key, payee_key]
        senders += [payer, payee]
        times += ["2100-01-01T00:00:00Z", "2100-01-01T00:00:01Z"]
    else:
        rail.claim(secret, offer["refundAfterMs"] - 1)
        terminal = {"type": "reveal", "from": payee, "contract": accept["contract"], "secret": secret}
        receipt = {"type": "receipt", "from": payer, "contract": accept["contract"], "outcome": "claimed"}
        frames += [terminal, receipt]
        keys += [payee_key, payer_key]
        senders += [payee, payer]
        times += ["2099-12-31T23:53:00Z", "2099-12-31T23:54:00Z"]

    messages = [signed_message(i + 1, keys[i], senders[i], frame, times[i]) for i, frame in enumerate(frames)]
    batch = {
        "status": "ok", "generation": 11, "starting_cursor": 0,
        "proposed_cursor": len(messages), "count": len(messages),
        "first_seq": 1, "last_seq": len(messages), "messages": messages,
    }
    result = validator.validate_transcript(batch, ROOM)
    return result, rail, secret


claim_result, claim_rail, claim_secret = lifecycle(False)
assert claim_rail.status == "claimed"
assert claim_result["contracts"][0]["status"] == "claimed"
assert claim_secret not in validator.canonical(claim_result)

refund_result, refund_rail, refund_secret = lifecycle(True)
assert refund_rail.status == "refunded"
assert refund_result["contracts"][0]["status"] == "refunded"
assert refund_secret not in validator.canonical(refund_result)

try:
    LocalPaperRail("0x" + "00" * 32, 100).claim("0x" + "01" * 32, 99)
except ValueError:
    pass
else:
    raise AssertionError("PaperRail accepted an incorrect secret")

try:
    LocalPaperRail("0x" + "00" * 32, 100).refund(99)
except ValueError:
    pass
else:
    raise AssertionError("PaperRail accepted an early refund")

print("PASS: zero-value PaperRail claim lifecycle validated")
print("PASS: zero-value PaperRail refund lifecycle validated")
print("PASS: PaperRail refused incorrect secret and early refund")
print("PASS: redacted summaries retained no unrevealed secret")
print("All local PaperRail lifecycle checks passed.")
