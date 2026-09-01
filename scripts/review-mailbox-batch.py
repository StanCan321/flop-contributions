#!/usr/bin/env python3
"""Fail-closed, side-effect-free review of one saved Technocore mailbox batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import NoReturn

MAX_BATCH_BYTES = 2 * 1024 * 1024
MAX_MESSAGES = 200
MAX_TEXT_CHARS = 4096
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_NONCE = 9_999_999_999_999_999_999
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
SIG_RE = re.compile(r"^[A-Za-z0-9_-]{85}[AQgw]$")
URL_RE = re.compile(r"(?:https?|ftp)://|\bwww\.", re.IGNORECASE)
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
BATCH_KEYS = {
    "status",
    "generation",
    "starting_cursor",
    "proposed_cursor",
    "count",
    "first_seq",
    "last_seq",
    "messages",
}
MESSAGE_KEYS = {"seq", "from", "ts", "nonce", "text", "sig"}


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def bounded_integer(value: object, maximum: int = MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and 0 <= value <= maximum


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json_object(path: Path, label: str, byte_limit: int | None = None) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            fail(f"{label} must be a regular file, not a symlink")
        if byte_limit is not None and path.stat().st_size > byte_limit:
            fail(f"{label} exceeds {byte_limit} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid JSON from {label}: {exc}")

    if not isinstance(payload, dict):
        fail(f"{label} must contain one JSON object")
    return payload


def require_private_file(path: Path, label: str) -> None:
    try:
        details = path.stat()
    except OSError as exc:
        fail(f"cannot inspect {label}: {exc}")
    if details.st_uid != os.getuid():
        fail(f"{label} must be owned by the current user")
    if stat.S_IMODE(details.st_mode) & 0o077:
        fail(f"{label} must not be accessible by group or other users")


def read_room(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            fail("mailbox capability file must be a regular file, not a symlink")
        room = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read mailbox capability file: {exc}")

    if not ROOM_RE.fullmatch(room):
        fail("mailbox capability file contains an invalid room name")
    return room


def verify_signature(verifier: Path, room: str, message: dict) -> None:
    if verifier.is_symlink() or not verifier.is_file():
        fail("envelope verifier must be a regular file, not a symlink")

    envelope = json.dumps(
        {
            "room": room,
            "nonce": str(message["nonce"]),
            "text": message["text"],
            "did": message["from"],
            "sig": message["sig"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

    try:
        result = subprocess.run(
            [sys.executable, str(verifier)],
            input=envelope,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        fail(f"signature verifier could not complete for message seq {message['seq']}")

    if result.returncode != 0:
        fail(f"signature verification failed for message seq {message['seq']}")


def validate_batch(batch: dict, room: str, verifier: Path) -> dict:
    if set(batch) != BATCH_KEYS:
        fail("batch fields do not match the trusted poll-output schema")
    if batch["status"] != "ok":
        fail("only a status=ok poll batch can be reviewed")

    generation = batch["generation"]
    starting = batch["starting_cursor"]
    proposed = batch["proposed_cursor"]
    count = batch["count"]
    first_seq = batch["first_seq"]
    last_seq = batch["last_seq"]
    messages = batch["messages"]

    for label, value in (
        ("generation", generation),
        ("starting_cursor", starting),
        ("proposed_cursor", proposed),
        ("count", count),
        ("last_seq", last_seq),
    ):
        if not bounded_integer(value):
            fail(f"{label} must be a bounded nonnegative integer")

    if not isinstance(messages, list) or len(messages) > MAX_MESSAGES:
        fail("messages must be an array of at most 200 records")
    if count != len(messages):
        fail("count does not match the number of messages")
    if proposed != last_seq or proposed < starting:
        fail("proposed cursor and last sequence are inconsistent")

    if messages:
        if not bounded_integer(first_seq) or first_seq != messages[0].get("seq"):
            fail("first sequence does not match the first message")
    elif first_seq is not None or proposed != starting:
        fail("empty batch cursor fields are inconsistent")

    reviewed: list[dict] = []
    previous_seq = starting
    seen_signatures: set[str] = set()

    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != MESSAGE_KEYS:
            fail(f"message {index} fields do not match the trusted schema")

        seq = message["seq"]
        sender = message["from"]
        timestamp = message["ts"]
        nonce = message["nonce"]
        text = message["text"]
        signature = message["sig"]

        if not bounded_integer(seq) or seq <= previous_seq or seq > proposed:
            fail(f"message {index} has an invalid or non-increasing sequence")
        if not (index == 0 and starting == 0) and seq != previous_seq + 1:
            fail(f"message seq {seq} follows an unexpected sequence gap")
        if not isinstance(sender, str) or not DID_RE.fullmatch(sender):
            fail(f"message seq {seq} does not contain an Ed25519 did:key sender")
        if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 64:
            fail(f"message seq {seq} has an invalid timestamp")
        if not bounded_integer(nonce, MAX_NONCE):
            fail(f"message seq {seq} has an invalid nonce")
        if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT_CHARS:
            fail(f"message seq {seq} has invalid text")
        if any(unicodedata.category(char) in INVISIBLE_CATEGORIES for char in text):
            fail(f"message seq {seq} contains control or invisible characters")
        if not isinstance(signature, str) or not SIG_RE.fullmatch(signature):
            fail(f"message seq {seq} has no canonical retained signature")

        verify_signature(verifier, room, message)

        signature_hash = sha256_text(signature)
        if signature_hash in seen_signatures:
            fail(f"same-batch signed replay detected at message seq {seq}")
        seen_signatures.add(signature_hash)

        canonical = f"{room}|{nonce}|{text}"
        reviewed.append(
            {
                "seq": seq,
                "sender_sha256": sha256_text(sender),
                "message_sha256": sha256_text(text),
                "envelope_sha256": sha256_text(canonical),
                "signature_sha256": signature_hash,
                "contains_url": bool(URL_RE.search(text)),
            }
        )
        previous_seq = seq

    if messages and previous_seq != proposed:
        fail("last reviewed sequence does not equal the proposed cursor")

    digest_source = json.dumps(
        {
            "generation": generation,
            "starting_cursor": starting,
            "proposed_cursor": proposed,
            "messages": reviewed,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    return {
        "schema_version": 1,
        "generation": generation,
        "starting_cursor": starting,
        "proposed_cursor": proposed,
        "count": count,
        "batch_sha256": sha256_text(digest_source),
        "signature_status": "all_valid" if messages else "no_messages",
        "ack_eligible": bool(messages),
        "ack_cursor": proposed if messages else None,
        "url_count": sum(item["contains_url"] for item in reviewed),
        "messages": reviewed,
    }


def reject_historical_replays(receipt: dict, history_dir: Path) -> None:
    if history_dir.is_symlink():
        fail("review history directory must not be a symlink")
    history_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(history_dir, 0o700)

    current = {item["signature_sha256"]: item["seq"] for item in receipt["messages"]}
    generation = receipt["generation"]

    for path in history_dir.glob("*.json"):
        old = load_json_object(
            path, f"review history file {path.name}", MAX_BATCH_BYTES
        )
        if old.get("generation") != generation:
            continue
        for item in old.get("messages", []):
            if not isinstance(item, dict):
                fail(f"review history file {path.name} is malformed")
            signature_hash = item.get("signature_sha256")
            if signature_hash in current and item.get("seq") != current[signature_hash]:
                fail(
                    "same-generation signed replay detected against archived "
                    f"receipt {path.name}"
                )


def write_receipt(path: Path, receipt: dict) -> None:
    if path.is_symlink():
        fail("receipt path must not be a symlink")

    encoded = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)

    if path.exists():
        try:
            if path.read_bytes() == encoded:
                return
        except OSError as exc:
            fail(f"cannot read existing receipt: {exc}")
        fail("existing receipt does not match this reviewed batch")

    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        fail(f"cannot write receipt atomically: {exc}")


def parse_args() -> argparse.Namespace:
    home = Path.home()
    state = home / "flop"
    agent = home / "technocore-agent"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=state / "mailbox.batch.json")
    parser.add_argument("--receipt", type=Path, default=state / "mailbox.review.json")
    parser.add_argument("--history-dir", type=Path, default=state / "reviewed-batches")
    parser.add_argument("--room-file", type=Path, default=state / "mailbox.txt")
    parser.add_argument("--verifier", type=Path, default=agent / "verify-envelope.py")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_private_file(args.batch, "saved mailbox batch")
    require_private_file(args.room_file, "mailbox capability file")
    batch = load_json_object(args.batch, "saved mailbox batch", MAX_BATCH_BYTES)
    room = read_room(args.room_file)
    receipt = validate_batch(batch, room, args.verifier)
    reject_historical_replays(receipt, args.history_dir)
    write_receipt(args.receipt, receipt)
    json.dump(receipt, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
