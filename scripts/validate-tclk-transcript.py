#!/usr/bin/env python3
"""Read-only, fail-closed validator for hash-lock tclk/1 mailbox transcripts.

This is an independent parser, not a wallet or settlement client. It never posts,
acknowledges, opens URLs, invokes message text, or retains revealed secrets.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PREFIX = "tclk1 "
DOMAIN = "FLOP::tclk::v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_CHARS = 4096
MAX_SAFE_INTEGER = 9_007_199_254_740_991
DID = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
HEX32 = re.compile(r"^0x[0-9a-f]{64}$")
AMOUNT = re.compile(r"^[1-9][0-9]*$")
ASSET = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RAIL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
NONCE = re.compile(r"^[0-9a-f]{8,64}$")
ROOM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
TRANSPORT_NONCE = re.compile(r"^[0-9]{1,19}$")
SIGNATURE = re.compile(r"^[A-Za-z0-9_-]{86}$")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BATCH_KEYS = {
    "status", "generation", "starting_cursor", "proposed_cursor", "count",
    "first_seq", "last_seq", "messages",
}
MESSAGE_KEYS = {"seq", "from", "ts", "nonce", "text", "sig"}

FRAME_KEYS = {
    "offer": (
        {"type", "from", "role", "amount", "asset", "lock", "rails",
         "claimByMs", "refundAfterMs", "expiresMs", "paymentKey", "job", "nonce", "id"},
        {"type", "from", "role", "amount", "asset", "lock", "rails",
         "claimByMs", "refundAfterMs", "expiresMs", "nonce", "id"},
    ),
    "accept": (
        {"type", "from", "ref", "statement", "contract", "paymentKey", "nonce"},
        {"type", "from", "ref", "statement", "contract", "nonce"},
    ),
    "lock": (
        {"type", "from", "contract", "rail", "ref", "presig"},
        {"type", "from", "contract", "rail", "ref"},
    ),
    "reveal": (
        {"type", "from", "contract", "secret"},
        {"type", "from", "contract", "secret"},
    ),
    "refund": (
        {"type", "from", "contract", "reason"},
        {"type", "from", "contract"},
    ),
    "cancel": (
        {"type", "from", "contract", "reason"},
        {"type", "from", "contract"},
    ),
    "receipt": (
        {"type", "from", "contract", "outcome", "rail", "ref"},
        {"type", "from", "contract", "outcome"},
    ),
}


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(tag: str, payload: object) -> str:
    material = f"{DOMAIN}|{tag}|{canonical(payload)}".encode("ascii")
    return "0x" + hashlib.sha256(material).hexdigest()


def redacted_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in B58:
            raise ValueError("DID is not canonical base58btc")
        number = number * 58 + B58.index(char)
    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + decoded


def verify_transport(room: str, message: dict) -> None:
    sender = message.get("from")
    nonce = message.get("nonce")
    text = message.get("text")
    signature_text = message.get("sig")
    if not isinstance(sender, str) or not DID.fullmatch(sender):
        raise ValueError("transport sender is not an Ed25519 did:key")
    if type(nonce) is not int or not TRANSPORT_NONCE.fullmatch(str(nonce)):
        raise ValueError("transport nonce is malformed")
    if not isinstance(text, str) or not isinstance(signature_text, str) or not SIGNATURE.fullmatch(signature_text):
        raise ValueError("transport text or retained signature is malformed")
    decoded_did = base58_decode(sender[len("did:key:z"):])
    if len(decoded_did) != 34 or not decoded_did.startswith(b"\xed\x01"):
        raise ValueError("DID does not contain one Ed25519 public key")
    try:
        signature = base64.b64decode(signature_text + "==", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("retained signature is not base64url") from exc
    if len(signature) != 64 or base64.urlsafe_b64encode(signature).decode().rstrip("=") != signature_text:
        raise ValueError("retained signature is not canonical")
    try:
        Ed25519PublicKey.from_public_bytes(decoded_did[2:]).verify(
            signature, f"{room}|{nonce}|{text}".encode("utf-8")
        )
    except InvalidSignature as exc:
        raise ValueError("transport signature verification failed") from exc


def require_string(frame: dict, name: str, pattern: re.Pattern | None = None) -> str:
    value = frame.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        raise ValueError(f"{name} is malformed")
    return value


def require_ms(frame: dict, name: str) -> int:
    value = frame.get(name)
    if type(value) is not int or not 0 < value <= MAX_SAFE_INTEGER:
        raise ValueError(f"{name} must be a positive safe unix-ms integer")
    return value


def parse_time(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("transport timestamp must be an ISO-8601 UTC string")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1000)


def validate_job(value: object) -> None:
    if not isinstance(value, dict) or not {"proto", "id"} <= set(value):
        raise ValueError("job must contain proto and id")
    if set(value) - {"proto", "id", "context"}:
        raise ValueError("job contains an unknown field")
    proto = value.get("proto")
    if not isinstance(proto, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", proto):
        raise ValueError("job.proto is malformed")
    if not isinstance(value.get("id"), str) or not value["id"]:
        raise ValueError("job.id is malformed")
    if "context" in value and (not isinstance(value["context"], str) or not value["context"]):
        raise ValueError("job.context is malformed")


def validate_frame(frame: object) -> dict:
    if not isinstance(frame, dict):
        raise ValueError("frame must be an object")
    kind = frame.get("type")
    if kind not in FRAME_KEYS:
        raise ValueError("unknown frame type")
    allowed, required = FRAME_KEYS[kind]
    if set(frame) - allowed or not required <= set(frame):
        raise ValueError(f"{kind} fields do not match tclk/1")
    require_string(frame, "from", DID)

    if kind == "offer":
        if frame.get("role") not in {"payer", "payee"}:
            raise ValueError("offer role must be payer or payee")
        require_string(frame, "amount", AMOUNT)
        require_string(frame, "asset", ASSET)
        if frame.get("lock") != "hash":
            raise ValueError("only hash-lock tclk/1 transcripts are supported")
        rails = frame.get("rails")
        if not isinstance(rails, list) or not rails or any(
            not isinstance(item, str) or not RAIL.fullmatch(item) for item in rails
        ):
            raise ValueError("offer rails are malformed")
        claim = require_ms(frame, "claimByMs")
        refund = require_ms(frame, "refundAfterMs")
        require_ms(frame, "expiresMs")
        if claim >= refund:
            raise ValueError("claimByMs must precede refundAfterMs")
        if "paymentKey" in frame:
            raise ValueError("paymentKey is not accepted by this hash-only validator")
        if "job" in frame:
            validate_job(frame["job"])
        require_string(frame, "nonce", NONCE)
        offer_id = require_string(frame, "id", HEX32)
        fields = {key: value for key, value in frame.items() if key != "id"}
        if offer_id != digest("offer", fields):
            raise ValueError("offer id mismatch")
    elif kind == "accept":
        require_string(frame, "ref", HEX32)
        require_string(frame, "statement", HEX32)
        require_string(frame, "contract", HEX32)
        require_string(frame, "nonce", NONCE)
        if "paymentKey" in frame:
            raise ValueError("paymentKey is not accepted by this hash-only validator")
    else:
        require_string(frame, "contract", HEX32)
        if kind == "lock":
            require_string(frame, "rail", RAIL)
            require_string(frame, "ref")
            if "presig" in frame:
                raise ValueError("PTLC pre-signatures are unsupported")
        elif kind == "reveal":
            require_string(frame, "secret", HEX32)
        elif kind in {"refund", "cancel"} and "reason" in frame:
            require_string(frame, "reason")
        elif kind == "receipt":
            if frame.get("outcome") not in {"claimed", "refunded", "cancelled"}:
                raise ValueError("receipt outcome is malformed")
            if "rail" in frame:
                require_string(frame, "rail", RAIL)
            if "ref" in frame:
                require_string(frame, "ref")
    return frame


def decode_line(text: object) -> dict | None:
    if not isinstance(text, str):
        raise ValueError("transport text must be a string")
    if not text.startswith(PREFIX):
        return None
    if len(text) > MAX_CHARS or not all(0x20 <= ord(char) <= 0x7E for char in text):
        raise ValueError("tclk line exceeds limits or is not printable ASCII")
    body = text[len(PREFIX):]
    parsed = json.loads(body, object_pairs_hook=reject_duplicates)
    frame = validate_frame(parsed)
    if body != canonical(frame):
        raise ValueError("tclk frame is not canonical JSON")
    return frame


@dataclass
class Contract:
    offer: dict
    status: str = "proposed"
    payer: str | None = None
    payee: str | None = None
    contract: str | None = None
    statement: str | None = None
    rail: str | None = None

    def __post_init__(self) -> None:
        if self.offer["role"] == "payer":
            self.payer = self.offer["from"]
        else:
            self.payee = self.offer["from"]

    def apply(self, frame: dict, now_ms: int) -> None:
        kind = frame["type"]
        if kind == "offer":
            raise ValueError("additional offer cannot enter an open contract")
        if kind == "accept":
            if self.status != "proposed" or frame["ref"] != self.offer["id"]:
                raise ValueError("accept is out of turn or names another offer")
            if frame["from"] == self.offer["from"] or now_ms >= self.offer["expiresMs"]:
                raise ValueError("self-accept or expired offer")
            core = {key: frame[key] for key in ("from", "ref", "statement", "nonce")}
            expected = digest("contract", {"offer": self.offer, "accept": core})
            if frame["contract"] != expected:
                raise ValueError("contract id mismatch")
            self.contract, self.statement = expected, frame["statement"]
            if self.offer["role"] == "payer":
                self.payee = frame["from"]
            else:
                self.payer = frame["from"]
            self.status = "accepted"
        elif kind == "lock":
            if self.status != "accepted" or frame["contract"] != self.contract:
                raise ValueError("lock is out of turn or names another contract")
            if frame["from"] != self.payer or frame["rail"] not in self.offer["rails"]:
                raise ValueError("lock has the wrong party or an unoffered rail")
            self.rail, self.status = frame["rail"], "locked"
        elif kind == "reveal":
            if self.status != "locked" or frame["contract"] != self.contract:
                raise ValueError("reveal is out of turn or names another contract")
            if frame["from"] != self.payee or now_ms >= self.offer["refundAfterMs"]:
                raise ValueError("reveal has the wrong party or is too late")
            opened = "0x" + hashlib.sha256(bytes.fromhex(frame["secret"][2:])).hexdigest()
            if opened != self.statement:
                raise ValueError("secret does not open the statement")
            self.status = "claimed"
        elif kind == "refund":
            if self.status != "locked" or frame["contract"] != self.contract:
                raise ValueError("refund is out of turn or names another contract")
            if frame["from"] != self.payer or now_ms < self.offer["refundAfterMs"]:
                raise ValueError("refund has the wrong party or is too early")
            self.status = "refunded"
        elif kind == "cancel":
            if self.status == "proposed":
                raise ValueError("proposed-state cancel is deferred pending tclk spec clarification")
            if self.status != "accepted" or frame["contract"] != self.contract:
                raise ValueError("cancel is out of turn or names another contract")
            if frame["from"] not in {self.payer, self.payee}:
                raise ValueError("cancel is from a non-party")
            self.status = "cancelled"
        elif kind == "receipt":
            if self.status not in {"claimed", "refunded", "cancelled"}:
                raise ValueError("receipt precedes a terminal state")
            if frame["contract"] != self.contract or frame["from"] not in {self.payer, self.payee}:
                raise ValueError("receipt names another contract or a non-party")
            if frame["outcome"] != self.status:
                raise ValueError("receipt outcome contradicts the terminal state")


def validate_transcript(payload: object, room: str) -> dict:
    if not isinstance(payload, dict) or set(payload) != BATCH_KEYS:
        raise ValueError("input fields do not match the saved mailbox batch schema")
    if payload["status"] != "ok":
        raise ValueError("only a status=ok saved mailbox batch can be validated")
    generation = payload["generation"]
    starting = payload["starting_cursor"]
    proposed = payload["proposed_cursor"]
    count = payload["count"]
    first_seq = payload["first_seq"]
    last_seq = payload["last_seq"]
    messages = payload["messages"]
    for name, value in (
        ("generation", generation), ("starting_cursor", starting),
        ("proposed_cursor", proposed), ("count", count), ("last_seq", last_seq),
    ):
        if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
            raise ValueError(f"{name} must be a bounded nonnegative integer")
    if not isinstance(messages, list) or count != len(messages):
        raise ValueError("count does not match the messages array")
    if proposed != last_seq or proposed < starting:
        raise ValueError("proposed cursor and last sequence are inconsistent")
    if messages:
        if type(first_seq) is not int or first_seq != messages[0].get("seq"):
            raise ValueError("first sequence does not match the first message")
    elif first_seq is not None or proposed != starting:
        raise ValueError("empty batch cursor fields are inconsistent")

    contracts: dict[str, Contract] = {}
    contract_by_id: dict[str, Contract] = {}
    seen_lines: set[str] = set()
    ignored = 0
    accepted = 0
    previous_seq = starting

    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != MESSAGE_KEYS:
            raise ValueError("transport message fields do not match the saved-batch schema")
        seq = message.get("seq")
        if type(seq) is not int or not 0 < seq <= MAX_SAFE_INTEGER:
            raise ValueError("transport sequence is malformed")
        if seq <= previous_seq or seq > proposed:
            raise ValueError("transport sequence is outside the batch cursor range")
        if not (index == 0 and starting == 0) and seq != previous_seq + 1:
            raise ValueError("transport transcript contains a sequence gap or replay")
        previous_seq = seq
        verify_transport(room, message)
        frame = decode_line(message.get("text"))
        if frame is None:
            ignored += 1
            continue
        if message["text"] in seen_lines:
            raise ValueError("duplicate or replayed tclk frame")
        seen_lines.add(message["text"])
        if message.get("from") != frame["from"] or not DID.fullmatch(str(message.get("from", ""))):
            raise ValueError("frame sender does not match transport-verified sender")
        now_ms = parse_time(message.get("ts"))
        if frame["type"] == "offer":
            if frame["id"] in contracts:
                raise ValueError("duplicate or replayed offer")
            state = Contract(frame)
            contracts[frame["id"]] = state
        elif frame["type"] == "accept":
            state = contracts.get(frame["ref"])
            if state is None:
                raise ValueError("accept appears before its offer")
            state.apply(frame, now_ms)
            contract_by_id[frame["contract"]] = state
        else:
            state = contract_by_id.get(frame["contract"])
            if state is None:
                raise ValueError("frame appears before its accepted contract")
            state.apply(frame, now_ms)
        accepted += 1

    if messages and previous_seq != proposed:
        raise ValueError("last message sequence does not match the proposed cursor")

    binding = {
        "generation": generation,
        "starting_cursor": starting,
        "proposed_cursor": proposed,
        "count": count,
        "first_seq": first_seq,
        "last_seq": last_seq,
    }

    return {
        "schema_version": 2,
        "protocol": "tclk/1",
        "mode": "read_only_hash_lock",
        **binding,
        "batch_binding_sha256": redacted_hash(canonical(binding)),
        "accepted_frame_count": accepted,
        "ignored_non_tclk_count": ignored,
        "contracts": [
            {
                "offer_sha256": redacted_hash(offer_id),
                "contract_sha256": redacted_hash(state.contract) if state.contract else None,
                "status": state.status,
                "rail": state.rail,
            }
            for offer_id, state in sorted(contracts.items())
        ],
        "side_effects": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="saved Technocore mailbox batch JSON")
    parser.add_argument("--room", required=True, help="room whose signed envelopes are verified")
    args = parser.parse_args()
    try:
        if not ROOM.fullmatch(args.room):
            fail("room name is malformed")
        if args.batch.is_symlink() or not args.batch.is_file():
            fail("batch must be a regular file, not a symlink")
        if args.batch.stat().st_size > MAX_BYTES:
            fail("batch exceeds the 2 MiB review limit")
        payload = json.loads(
            args.batch.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
        print(json.dumps(validate_transcript(payload, args.room), sort_keys=True, indent=2))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
