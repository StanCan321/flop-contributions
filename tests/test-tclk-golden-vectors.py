#!/usr/bin/env python3
"""Independent checks against flop-labs/tclk's fixed tclk/1 wire vectors.

Source checked at upstream commit 1459b78e3b981bbac67f845784c885b3b1ad85ba.
The fetched tests/vectors.test.ts SHA-256 was
c60f109ba26547c6be0795b0eb66a861a96a7d68a36885a28f318e69a1cebb96.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate-tclk-transcript.py"
SPEC = importlib.util.spec_from_file_location("tclk_validator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

PAYER = "did:key:z6Mk" + "f" * 44
PAYEE = "did:key:z6Mk" + "g" * 44
OFFER_ID = "0xd001fbbf4fa36d9ab8ea88df02a8b3303539e9d59f7ff9d9bfeb679318e9ce75"
CONTRACT_ID = "0x2768bf32b455317879796093ff2e5882371cbec238611ca71f555a7fcbe58e1c"
NON_ASCII_OFFER_ID = "0xfdad69c602bef151596e3e914cc3ca05b1ccd009211b57c4fdbf0ba0e0d4635b"

OFFER_LINE = (
    'tclk1 {"amount":"1000000","asset":"FLOP","claimByMs":1756703600000,'
    '"expiresMs":1756700600000,'
    f'"from":"{PAYER}","id":"{OFFER_ID}",'
    '"job":{"context":"ctx-1","id":"task-3f","proto":"a2a"},"lock":"hash",'
    '"nonce":"9f2c81d04c9e1f7a","rails":["flop-htlc","x402"],'
    '"refundAfterMs":1756707200000,"role":"payer","type":"offer"}'
)
ACCEPT_LINE = (
    f'tclk1 {{"contract":"{CONTRACT_ID}","from":"{PAYEE}",'
    f'"nonce":"0011223344556677","ref":"{OFFER_ID}",'
    '"statement":"0xabababababababababababababababababababababababababababababababab",'
    '"type":"accept"}'
)

offer = validator.decode_line(OFFER_LINE)
accept = validator.decode_line(ACCEPT_LINE)
assert offer is not None and accept is not None
assert offer["id"] == OFFER_ID
assert accept["contract"] == CONTRACT_ID

state = validator.Contract(offer)
state.apply(accept, 1_756_700_500_000)
assert state.status == "accepted"
assert state.contract == CONTRACT_ID

non_ascii_fields = {
    "type": "offer",
    "from": PAYER,
    "role": "payer",
    "lock": "hash",
    "amount": "100",
    "asset": "FLOP",
    "rails": ["flop-htlc"],
    "claimByMs": 1_756_703_600_000,
    "refundAfterMs": 1_756_707_200_000,
    "expiresMs": 1_756_700_600_000,
    "job": {"proto": "a2a", "id": "t\u00e2che-1"},
    "nonce": "9f2c81d04c9e1f7a",
}
assert validator.digest("offer", non_ascii_fields) == NON_ASCII_OFFER_ID
encoded = validator.canonical({**non_ascii_fields, "id": NON_ASCII_OFFER_ID})
assert "\\u00e2" in encoded
assert encoded.isascii()

print("PASS: upstream offer id and canonical line match")
print("PASS: upstream contract id and acceptance match")
print("PASS: upstream escaped non-ASCII offer id matches")
print("All pinned tclk golden-vector checks passed.")
