# /// script
# requires-python = ">=3.12"
# dependencies = ["cryptography==50.0.1"]
# ///
"""Verify a Technocore signed room envelope supplied as JSON on standard input."""

from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import unicodedata

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
NONCE_RE = re.compile(r"^[0-9]{1,19}$")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MULTICODEC_ED25519 = b"\xed\x01"
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
MAX_TEXT_CHARS = 4096


def fail(message: str) -> None:
    print(f"INVALID: {message}", file=sys.stderr)
    raise SystemExit(1)


def clean_text(text: str) -> str:
    cleaned = "".join(
        " " if unicodedata.category(char) in INVISIBLE_CATEGORIES else char
        for char in text
    ).strip()

    if not cleaned:
        fail("message is empty after normalization")

    if len(cleaned) > MAX_TEXT_CHARS:
        fail("message exceeds the 4096-character limit after normalization")

    return cleaned


def base58btc_decode(value: str) -> bytes:
    if not value:
        fail("empty multibase payload")

    number = 0

    for char in value:
        try:
            digit = B58.index(char)
        except ValueError:
            fail("DID contains a character outside base58btc")

        number = number * 58 + digit

    decoded = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )

    leading_zeroes = len(value) - len(value.lstrip("1"))
    return (b"\x00" * leading_zeroes) + decoded


def public_key_from_did(did: str) -> Ed25519PublicKey:
    prefix = "did:key:z"

    if not did.startswith(prefix):
        fail("DID must use did:key with base58btc multibase")

    decoded = base58btc_decode(did[len(prefix) :])

    if not decoded.startswith(MULTICODEC_ED25519):
        fail("DID does not contain an Ed25519 public key")

    raw_key = decoded[len(MULTICODEC_ED25519) :]

    if len(raw_key) != 32:
        fail("Ed25519 public key must be exactly 32 bytes")

    return Ed25519PublicKey.from_public_bytes(raw_key)


def decode_signature(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]{86}", value):
        fail("signature must be 86 unpadded base64url characters")

    padding = "=" * (-len(value) % 4)

    try:
        signature = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        fail("signature is not valid base64url")

    if len(signature) != 64:
        fail("Ed25519 signature must be exactly 64 bytes")

    return signature


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"standard input is not valid JSON: {exc}")

    if not isinstance(payload, dict):
        fail("JSON input must be an object")

    room = payload.get("room")
    nonce = payload.get("nonce")
    text = payload.get("text")
    did = payload.get("did")
    signature_text = payload.get("sig")

    if not all(isinstance(value, str) for value in (room, nonce, text, did, signature_text)):
        fail("room, nonce, text, did, and sig must all be strings")

    if not ROOM_RE.fullmatch(room):
        fail("invalid room name")

    if not NONCE_RE.fullmatch(nonce):
        fail("nonce must contain 1-19 ASCII digits")

    normalized = clean_text(text)
    public_key = public_key_from_did(did)
    signature = decode_signature(signature_text)
    canonical = f"{room}|{nonce}|{normalized}".encode("utf-8")

    try:
        public_key.verify(signature, canonical)
    except InvalidSignature:
        fail("signature does not match the canonical envelope")

    print("VALID: Ed25519 signature matches the canonical Technocore envelope")


if __name__ == "__main__":
    main()
