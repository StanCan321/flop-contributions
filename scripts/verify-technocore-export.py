#!/usr/bin/env python3
"""Verify one byte-exact Technocore JSONL export without network or state changes."""

from __future__ import annotations

import argparse, base64, binascii, hashlib, json, re, sys
from pathlib import Path
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_BYTES = 16 * 1024 * 1024
MAX_SAFE_INTEGER = 9_007_199_254_740_991
ROOM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
DID = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
SIG = re.compile(r"^[A-Za-z0-9_-]{86}$")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
UNSIGNED_KEYS = {"seq", "from", "ts", "text"}
SIGNED_KEYS = UNSIGNED_KEYS | {"nonce", "sig"}

def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr); raise SystemExit(1)

def pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result: raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def b58(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in B58: raise ValueError("sender DID is not canonical base58btc")
        number = number * 58 + B58.index(char)
    raw = number.to_bytes((number.bit_length()+7)//8, "big") if number else b""
    return b"\0" * (len(value)-len(value.lstrip("1"))) + raw

def verify_signed(room: str, record: dict) -> None:
    sender, nonce, text, encoded = (record[k] for k in ("from", "nonce", "text", "sig"))
    if not isinstance(sender, str) or not DID.fullmatch(sender): raise ValueError("invalid signed sender")
    if type(nonce) is not int or not 0 <= nonce <= 9_999_999_999_999_999_999: raise ValueError("invalid signed nonce")
    if not isinstance(text, str) or not isinstance(encoded, str) or not SIG.fullmatch(encoded): raise ValueError("invalid signed record")
    raw_key = b58(sender.removeprefix("did:key:z"))
    if len(raw_key) != 34 or raw_key[:2] != b"\xed\x01": raise ValueError("DID is not Ed25519")
    try: signature = base64.b64decode(encoded + "==", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc: raise ValueError("signature is not base64url") from exc
    if len(signature) != 64 or base64.urlsafe_b64encode(signature).decode().rstrip("=") != encoded: raise ValueError("signature is not canonical")
    try: Ed25519PublicKey.from_public_bytes(raw_key[2:]).verify(signature, f"{room}|{nonce}|{text}".encode())
    except InvalidSignature as exc: raise ValueError("signature verification failed") from exc

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--room", required=True)
    parser.add_argument("--generation", required=True, type=int)
    args = parser.parse_args()
    try:
        if not ROOM.fullmatch(args.room): raise ValueError("invalid room")
        if not 0 <= args.generation <= MAX_SAFE_INTEGER: raise ValueError("invalid generation")
        if args.export.is_symlink() or not args.export.is_file(): raise ValueError("export must be a regular file")
        raw = args.export.read_bytes()
        if len(raw) > MAX_BYTES: raise ValueError("export exceeds 16 MiB")
        lines = raw.splitlines()
        previous = None; signed = 0
        for index, line in enumerate(lines, 1):
            record = json.loads(line.decode("utf-8"), object_pairs_hook=pairs)
            if not isinstance(record, dict) or set(record) not in (UNSIGNED_KEYS, SIGNED_KEYS): raise ValueError(f"record {index} has an invalid shape")
            seq = record["seq"]
            if type(seq) is not int or not 0 < seq <= MAX_SAFE_INTEGER: raise ValueError(f"record {index} has an invalid sequence")
            if previous is not None and seq != previous + 1: raise ValueError(f"record {index} breaks sequence continuity")
            if not isinstance(record["from"], str) or not isinstance(record["ts"], str) or not 1 <= len(record["ts"]) <= 64 or not isinstance(record["text"], str): raise ValueError(f"record {index} has invalid text metadata")
            if set(record) == SIGNED_KEYS: verify_signed(args.room, record); signed += 1
            previous = seq
        report = {"schema_version": 1, "mode": "read_only_export_verification", "room_sha256": hashlib.sha256(args.room.encode()).hexdigest(), "generation": args.generation, "first_seq": json.loads(lines[0])["seq"] if lines else None, "last_seq": previous, "count": len(lines), "signed_count": signed, "unsigned_count": len(lines)-signed, "export_sha256": hashlib.sha256(raw).hexdigest(), "side_effects": False}
        print(json.dumps(report, sort_keys=True, indent=2))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc: fail(str(exc))

if __name__ == "__main__": main()
