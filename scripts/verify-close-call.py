#!/usr/bin/env python3
"""Verify a frozen Close Call package and complete referee-room exports offline."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SAFE_INTEGER = 9_007_199_254_740_991
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
SIG_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ENVELOPE_KEYS = {"seq", "from", "ts", "text", "nonce", "sig"}
ROOM_TYPES = {
    "price": {"seed", "price", "final"},
    "flow": {"flow"},
    "state": {"state"},
    "positions": {"positions"},
    "pnl": {"pnl"},
}


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def reject_duplicates(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(raw: bytes, label: str) -> object:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not canonical JSON: {exc}") from exc


def read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"{label} exceeds 32 MiB")
    return raw


def decode_did(did: str) -> Ed25519PublicKey:
    if not DID_RE.fullmatch(did):
        raise ValueError("invalid referee DID")
    number = 0
    value = did.removeprefix("did:key:z")
    for char in value:
        if char not in B58:
            raise ValueError("referee DID is not canonical base58btc")
        number = number * 58 + B58.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        raise ValueError("referee DID is not an Ed25519 did:key")
    return Ed25519PublicKey.from_public_bytes(raw[2:])


def verify_envelope(room: str, record: dict) -> tuple[str, dict]:
    if set(record) != ENVELOPE_KEYS:
        raise ValueError(f"{room}: invalid Technocore envelope shape")
    seq, sender, timestamp, text, nonce, encoded = (
        record[key] for key in ("seq", "from", "ts", "text", "nonce", "sig")
    )
    if type(seq) is not int or not 0 < seq <= MAX_SAFE_INTEGER:
        raise ValueError(f"{room}: invalid sequence")
    if type(nonce) is not int or not 0 <= nonce <= 9_999_999_999_999_999_999:
        raise ValueError(f"{room}: invalid nonce")
    if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 64:
        raise ValueError(f"{room}: invalid timestamp")
    if not isinstance(text, str) or not isinstance(encoded, str) or not SIG_RE.fullmatch(encoded):
        raise ValueError(f"{room}: invalid signed fields")
    try:
        signature = base64.b64decode(encoded + "==", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{room}: signature is not base64url") from exc
    if len(signature) != 64 or base64.urlsafe_b64encode(signature).decode().rstrip("=") != encoded:
        raise ValueError(f"{room}: signature is not canonical")
    try:
        decode_did(sender).verify(signature, f"{room}|{nonce}|{text}".encode())
    except InvalidSignature as exc:
        raise ValueError(f"{room}: signature verification failed") from exc
    inner = load_json(text.encode(), f"{room} message {seq}")
    if not isinstance(inner, dict):
        raise ValueError(f"{room}: message {seq} is not an object")
    return sender, inner


def verify_package(package: Path, expected_hash: str, contest_id: str) -> tuple[dict, list[str]]:
    package_root = package.resolve()
    manifest_path = package / "manifest.json"
    raw_manifest = read_regular(manifest_path, "manifest")
    actual_hash = hashlib.sha256(raw_manifest).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"manifest SHA-256 mismatch: expected {expected_hash}, observed {actual_hash}")
    manifest = load_json(raw_manifest, "manifest")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    if manifest.get("package") != "technocore-close-call":
        raise ValueError("unexpected package name")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest has no files")
    entrypoint = manifest.get("entrypoint")
    if not isinstance(entrypoint, str) or entrypoint not in files:
        raise ValueError("manifest entrypoint is not a listed artifact")
    if "contest.json" not in files:
        raise ValueError("contest config is not a listed artifact")
    for name, metadata in files.items():
        if not isinstance(name, str) or not isinstance(metadata, dict):
            raise ValueError("invalid manifest artifact")
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != name:
            raise ValueError(f"unsafe artifact path: {name!r}")
        if metadata.get("url") != name:
            raise ValueError(f"artifact URL is not package-relative: {name}")
        expected_bytes, expected_file_hash = metadata.get("bytes"), metadata.get("sha256")
        if type(expected_bytes) is not int or expected_bytes < 0:
            raise ValueError(f"invalid artifact size: {name}")
        if not isinstance(expected_file_hash, str) or not HASH_RE.fullmatch(expected_file_hash):
            raise ValueError(f"invalid artifact hash: {name}")
        artifact = package / Path(*pure.parts)
        try:
            artifact.resolve(strict=True).relative_to(package_root)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise ValueError(f"artifact escapes the package: {name}") from exc
        raw = read_regular(artifact, f"artifact {name}")
        if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_file_hash:
            raise ValueError(f"artifact does not match manifest: {name}")
    contest_raw = read_regular(package / "contest.json", "contest config")
    contest = load_json(contest_raw, "contest config")
    if not isinstance(contest, dict) or contest.get("contest_id") != contest_id:
        raise ValueError("contest ID does not match the reviewed value")
    rooms = contest.get("rooms", {}).get("referee") if isinstance(contest.get("rooms"), dict) else None
    if not isinstance(rooms, list) or len(rooms) != len(ROOM_TYPES):
        raise ValueError("contest config does not name five referee rooms")
    if any(not isinstance(room, str) or not ROOM_RE.fullmatch(room) for room in rooms):
        raise ValueError("contest config contains an invalid referee room")
    if len(set(rooms)) != len(rooms):
        raise ValueError("contest config repeats a referee room")
    return manifest, rooms


def classify_rooms(rooms: list[str]) -> dict[str, str]:
    classified = {}
    for room in rooms:
        matches = [kind for kind in ROOM_TYPES if room.endswith(f"-{kind}")]
        if len(matches) != 1:
            raise ValueError(f"cannot classify referee room: {room}")
        classified[matches[0]] = room
    if set(classified) != set(ROOM_TYPES):
        raise ValueError("referee room roles are incomplete")
    return classified


def verify_exports(paths: dict[str, Path], roles: dict[str, str], expected_hash: str,
                   contest_id: str) -> dict:
    expected_rooms = set(roles.values())
    if set(paths) != expected_rooms:
        raise ValueError("exports must match the five configured referee rooms exactly")
    referee = None
    seed = None
    sweeps: dict[str, dict[int, str]] = {}
    counts = {}
    final_seen = False
    for kind, room in roles.items():
        raw = read_regular(paths[room], f"export for {room}")
        if not raw or not raw.endswith(b"\n"):
            raise ValueError(f"{room}: export must be nonempty and newline-terminated")
        previous_seq = 0
        room_sweeps: dict[int, str] = {}
        lines = raw.splitlines()
        for line_number, line in enumerate(lines, 1):
            record = load_json(line, f"{room} export line {line_number}")
            if not isinstance(record, dict):
                raise ValueError(f"{room}: envelope is not an object")
            sender, message = verify_envelope(room, record)
            if referee is None:
                referee = sender
            elif sender != referee:
                raise ValueError(f"{room}: referee DID changed")
            seq = record["seq"]
            if seq != previous_seq + 1:
                raise ValueError(f"{room}: export sequence is not complete at {seq}")
            previous_seq = seq
            message_type = message.get("t")
            if message_type not in ROOM_TYPES[kind]:
                raise ValueError(f"{room}: unexpected message type {message_type!r}")
            if message_type == "seed":
                if kind != "price" or seed is not None or seq != 1:
                    raise ValueError("seed must be the first and only seed in the price room")
                if message.get("season") != contest_id or message.get("package") != expected_hash:
                    raise ValueError("seed does not bind the reviewed contest and manifest")
                if message.get("rooms") != list(roles.values()):
                    raise ValueError("seed referee-room list differs from the package")
                seed = message
                continue
            if message_type == "final":
                if kind != "price" or final_seen or line_number != len(lines):
                    raise ValueError("final must be the last and only final price-room record")
                final_seen = True
                continue
            n, file_hash = message.get("n"), message.get("file")
            if type(n) is not int or n != len(room_sweeps) + 1:
                raise ValueError(f"{room}: sweep numbers are not complete")
            if not isinstance(file_hash, str) or not HASH_RE.fullmatch(file_hash):
                raise ValueError(f"{room}: sweep {n} has no valid file commitment")
            room_sweeps[n] = file_hash
        sweeps[kind] = room_sweeps
        counts[room] = len(lines)
    if seed is None or referee is None:
        raise ValueError("signed launch seed is missing")
    latest = {max(values, default=0) for values in sweeps.values()}
    if len(latest) != 1:
        raise ValueError("referee rooms end at different sweeps")
    latest_sweep = latest.pop()
    for n in range(1, latest_sweep + 1):
        commitments = {room_sweeps[n] for room_sweeps in sweeps.values()}
        if len(commitments) != 1:
            raise ValueError(f"referee file commitments disagree at sweep {n}")
    return {
        "referee_did_sha256": hashlib.sha256(referee.encode()).hexdigest(),
        "latest_sweep": latest_sweep,
        "final_present": final_seen,
        "record_counts": counts,
    }


def parse_export(value: str) -> tuple[str, Path]:
    room, separator, path = value.partition("=")
    if not separator or not ROOM_RE.fullmatch(room) or not path:
        raise argparse.ArgumentTypeError("expected ROOM=PATH")
    return room, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--contest-id", required=True)
    parser.add_argument("--room-export", action="append", required=True, type=parse_export)
    args = parser.parse_args()
    try:
        if not HASH_RE.fullmatch(args.expected_manifest_sha256):
            raise ValueError("expected manifest SHA-256 must be 64 lowercase hex characters")
        if not args.package.is_dir() or args.package.is_symlink():
            raise ValueError("package must be a real directory")
        _, rooms = verify_package(args.package, args.expected_manifest_sha256, args.contest_id)
        paths = dict(args.room_export)
        if len(paths) != len(args.room_export):
            raise ValueError("a room export was supplied more than once")
        evidence = verify_exports(paths, classify_rooms(rooms), args.expected_manifest_sha256,
                                  args.contest_id)
        report = {
            "schema_version": 1,
            "mode": "offline_close_call_verification",
            "contest_id": args.contest_id,
            "manifest_sha256": args.expected_manifest_sha256,
            **evidence,
            "limitations": [
                "visible referee exports do not reveal identifiers omitted from summary messages",
                "hash-committed sweep files were not verified unless supplied as package artifacts",
                "verification proves signatures and consistency, not organizer identity or fairness",
            ],
            "network_access": False,
            "side_effects": False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, UnicodeError, ValueError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
