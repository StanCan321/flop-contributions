#!/usr/bin/env python3
"""Verify local Close Call archive records against signed referee commitments offline."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys


SPEC = importlib.util.spec_from_file_location(
    "close_call_verifier", Path(__file__).with_name("verify-close-call.py")
)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
HASH = re.compile(r"^[0-9a-f]{64}$")
FULL_KEYS = {"bytes", "file", "n", "path", "status"}
REDACTED_KEYS = FULL_KEYS | {"redacted", "sha256"}
MAX_BYTES = 32 * 1024 * 1024


def read(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{label} exceeds 32 MiB")
    return raw


def load(raw: bytes, label: str):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=verifier.reject_duplicates,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ValueError(f"non-finite JSON: {value}")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid JSON: {exc}") from exc


def parse_record(value: str) -> tuple[int, Path]:
    sweep, separator, path = value.partition("=")
    if not separator or not sweep.isdecimal() or int(sweep) < 1 or not path:
        raise argparse.ArgumentTypeError("expected SWEEP=PATH")
    return int(sweep), Path(path)


def validate_index(index: object, contest_id: str) -> list[dict]:
    if not isinstance(index, dict) or set(index) != {"contest", "sweeps"}:
        raise ValueError("index has an unexpected shape")
    if index["contest"] != contest_id or not isinstance(index["sweeps"], list):
        raise ValueError("index contest does not match")
    entries = index["sweeps"]
    for expected_n, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or entry.get("n") != expected_n:
            raise ValueError(f"index is not contiguous at sweep {expected_n}")
        status = entry.get("status")
        expected_keys = FULL_KEYS if status == "full" else REDACTED_KEYS if status == "redacted" else set()
        if set(entry) != expected_keys:
            raise ValueError(f"sweep {expected_n} has an invalid index entry")
        if type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_BYTES:
            raise ValueError(f"sweep {expected_n} has an invalid size")
        if not isinstance(entry["file"], str) or not HASH.fullmatch(entry["file"]):
            raise ValueError(f"sweep {expected_n} has an invalid commitment")
        pure = PurePosixPath(entry["path"])
        if pure.is_absolute() or ".." in pure.parts or str(pure) != entry["path"]:
            raise ValueError(f"sweep {expected_n} has an unsafe path")
        if status == "full":
            if entry["path"] != f"sweeps/{entry['file']}.json":
                raise ValueError(f"sweep {expected_n} has an unexpected full-record path")
        else:
            if (entry["path"] != f"redacted/{entry['file']}.json"
                    or type(entry["redacted"]) is not int or entry["redacted"] < 1
                    or not isinstance(entry["sha256"], str) or not HASH.fullmatch(entry["sha256"])):
                raise ValueError(f"sweep {expected_n} has invalid redaction metadata")
    return entries


def verify_commitments(entries: list[dict], directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("signed flow directory must be a real directory")
    for entry in entries:
        n = entry["n"]
        raw = read(directory / f"{n:016d}.json", f"signed flow record {n}")
        envelope = load(raw, f"signed flow record {n}")
        if not isinstance(envelope, dict):
            raise ValueError(f"signed flow record {n} is not an object")
        _, payload = verifier.verify_envelope("d-close1-flow", envelope)
        if payload.get("t") != "flow" or payload.get("n") != n:
            raise ValueError(f"signed flow record {n} has the wrong payload")
        if payload.get("file") != entry["file"]:
            raise ValueError(f"archive commitment differs from signed sweep {n}")


def verify_records(records: dict[int, Path], entries: list[dict]) -> dict:
    details, full, redacted = [], 0, 0
    for n, path in sorted(records.items()):
        if n > len(entries):
            raise ValueError(f"record sweep {n} is absent from the index")
        entry = entries[n - 1]
        raw = read(path, f"archive record {n}")
        expected = entry["file"] if entry["status"] == "full" else entry["sha256"]
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"archive record {n} does not match its index digest and size")
        record = load(raw, f"archive record {n}")
        if (not isinstance(record, dict) or not isinstance(record.get("input"), dict)
                or not isinstance(record.get("output"), dict)
                or record["input"].get("n") != n or record["output"].get("sweep") != n
                or not isinstance(record["output"].get("minted"), list)):
            raise ValueError(f"archive record {n} has an invalid sweep shape")
        full += entry["status"] == "full"
        redacted += entry["status"] == "redacted"
        details.append({"n": n, "status": entry["status"],
                        "record_sha256": hashlib.sha256(raw).hexdigest(),
                        "minted_count": len(record["output"]["minted"])})
    return {"verified_records": details, "full_records": full, "redacted_records": redacted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--signed-flow-directory", required=True, type=Path)
    parser.add_argument("--contest-id", required=True)
    parser.add_argument("--record", action="append", default=[], type=parse_record)
    args = parser.parse_args()
    try:
        index = load(read(args.index, "archive index"), "archive index")
        entries = validate_index(index, args.contest_id)
        records = dict(args.record)
        if len(records) != len(args.record):
            raise ValueError("an archive sweep was supplied more than once")
        verify_commitments(entries, args.signed_flow_directory)
        report = {
            "schema_version": 1, "mode": "offline_close_call_archive_verification",
            "contest_id": args.contest_id, "index_sha256": hashlib.sha256(
                read(args.index, "archive index")).hexdigest(),
            "indexed_sweeps": len(entries), "signed_commitments_verified": len(entries),
            **verify_records(records, entries),
            "limitations": [
                "redacted record bytes do not hash to the referee's signed full-record commitment",
                "the archive index is organizer-published but is not itself signed by the referee",
                "records not explicitly supplied were commitment-checked but not downloaded or byte-checked",
            ],
            "network_access": False, "side_effects": False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
