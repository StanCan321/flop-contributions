#!/usr/bin/env python3
"""Offline hash-lock audit of a board export and one derived deal-room export."""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "tclk_cross_room_core", Path(__file__).with_name("validate-tclk-transcript.py")
)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)
LIMIT = 16 * 1024 * 1024
FIELDS = {"room", "generation", "first_seq", "last_seq", "sha256"}


def read_bounded(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("input exceeds 16 MiB")
    return raw


def load_export(path, descriptor):
    if not isinstance(descriptor, dict) or set(descriptor) != FIELDS:
        raise ValueError("invalid capture metadata shape")
    room = descriptor["room"]
    if not isinstance(room, str) or not core.ROOM.fullmatch(room):
        raise ValueError("invalid capture room")
    for field in ("generation", "first_seq", "last_seq"):
        value = descriptor[field]
        if type(value) is not int or not 0 <= value <= core.MAX_SAFE_INTEGER:
            raise ValueError("invalid capture integer")
    raw = read_bounded(path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != descriptor["sha256"]:
        raise ValueError("export does not match capture digest")
    records = []
    for line in raw.splitlines():
        record = json.loads(line, object_pairs_hook=core.reject_duplicates)
        if not isinstance(record, dict) or set(record) not in (
            core.MESSAGE_KEYS, {"seq", "from", "ts", "text"}
        ):
            raise ValueError("invalid export record shape")
        seq = record["seq"]
        if type(seq) is not int or seq != descriptor["first_seq"] + len(records):
            raise ValueError("export sequence gap, reorder, or replay")
        if not isinstance(record["text"], str) or len(record["text"]) > core.MAX_CHARS:
            raise ValueError("invalid record text")
        if not isinstance(record["from"], str):
            raise ValueError("invalid record sender")
        core.parse_time(record["ts"])
        if "sig" in record:
            core.verify_transport(room, record)
        records.append(record)
    if descriptor["first_seq"] < 1 or not records or records[-1]["seq"] != descriptor["last_seq"]:
        raise ValueError("empty or truncated export")
    return records


def audit(board_path, deal_path, capture, contract):
    if not isinstance(contract, str) or not core.HEX32.fullmatch(contract):
        raise ValueError("invalid target contract")
    if not isinstance(capture, dict) or set(capture) != {"board", "deal"}:
        raise ValueError("capture must describe board and deal exports")
    board = load_export(board_path, capture["board"])
    deal = load_export(deal_path, capture["deal"])
    if capture["board"]["room"] != "tclk-offers":
        raise ValueError("offer board room mismatch")
    if capture["deal"]["room"] != "mb-p-tclk-" + contract[2:18]:
        raise ValueError("derived deal room mismatch")
    offers = {}
    state = None
    seen = set()
    accepted_time = None
    counts = {"board": 0, "deal": 0}
    for source, records in (("board", board), ("deal", deal)):
        for record in records:
            if "sig" not in record or not record["text"].startswith(core.PREFIX):
                continue
            frame = core.decode_line(record["text"])
            if frame["from"] != record["from"]:
                raise ValueError("frame and transport sender differ")
            kind = frame["type"]
            if (source == "board") != (kind in {"offer", "accept"}):
                raise ValueError("frame is in the wrong protocol room")
            if record["text"] in seen:
                raise ValueError("replayed protocol frame")
            seen.add(record["text"])
            now = core.parse_time(record["ts"])
            if kind == "offer":
                offers[frame["id"]] = (frame, now, False)
            elif kind == "accept":
                if frame["ref"] not in offers:
                    raise ValueError("accept precedes its retained offer")
                offer, offered_time, bound = offers[frame["ref"]]
                if bound or now < offered_time:
                    raise ValueError("duplicate acceptance or reversed venue time")
                candidate = core.Contract(offer)
                candidate.apply(frame, now)
                offers[frame["ref"]] = (offer, offered_time, True)
                if frame["contract"] == contract:
                    state, accepted_time = candidate, now
            else:
                if state is None or frame["contract"] != contract:
                    raise ValueError("deal frame lacks the selected board acceptance")
                if now < accepted_time:
                    raise ValueError("deal timestamp precedes prior selected frame")
                state.apply(frame, now)
                accepted_time = now
            counts[source] += 1
    if state is None:
        raise ValueError("target contract acceptance missing")
    binding = {
        name: {**{key: value for key, value in item.items() if key != "room"},
               "room_sha256": core.redacted_hash(item["room"])}
        for name, item in capture.items()
    }
    return {"schema_version": 1, "mode": "offline_cross_room_hash_lock",
            "contract_sha256": core.redacted_hash(contract), "status": state.status,
            "captures": binding, "binding_sha256": core.redacted_hash(core.canonical(binding)),
            "frame_counts": counts, "venue_metadata_authenticated": False,
            "settlement_verified": False, "side_effects": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--deal", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--contract", required=True)
    args = parser.parse_args()
    try:
        capture = json.loads(read_bounded(args.capture), object_pairs_hook=core.reject_duplicates)
        print(json.dumps(audit(args.board, args.deal, capture, args.contract), sort_keys=True, indent=2))
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        core.fail("cross-room audit rejected input; verify captures, signatures, routing and transitions")


if __name__ == "__main__":
    main()
