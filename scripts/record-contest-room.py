#!/usr/bin/env python3
"""Append bounded read-only room snapshots; never sign, acknowledge, or prune."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.request
import uuid

SPEC = importlib.util.spec_from_file_location(
    "export_verifier", Path(__file__).with_name("verify-technocore-export.py")
)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
MAX_EXPORT = 32 * 1024 * 1024
MAX_STORAGE = 256 * 1024 * 1024
MAX_SNAPSHOTS = 1000
SNAPSHOT = re.compile(r"snapshot-[0-9]{6}-[0-9a-f]{32}")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True) + "\n").encode()


def decode(raw: bytes):
    def invalid_constant(value):
        raise ValueError("non-finite JSON")
    return json.loads(raw, object_pairs_hook=verifier.pairs,
                      parse_constant=invalid_constant)


def private(path: Path, directory: bool) -> None:
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("archive path has unsafe type or ownership")
    if stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise ValueError("archive paths require directories 700 and files 600")


def storage_size(root: Path) -> int:
    size = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            private(Path(parent) / name, True)
        for name in files:
            path = Path(parent) / name
            private(path, False)
            size += path.stat().st_size
    return size


def write_new(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused")


def fetch(room: str) -> tuple[bytes, dict]:
    # No environment proxies, cookies, credentials, user-provided host, or POST.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(f"https://technocore.chat/r/{room}/export", timeout=20) as reply:
        if reply.status != 200:
            raise ValueError("unexpected HTTP status")
        generation = reply.headers.get_all("X-Room-Generation", [])
        if len(generation) != 1 or not re.fullmatch(r"[0-9]{1,16}", generation[0]):
            raise ValueError("missing or ambiguous generation header")
        lengths = reply.headers.get_all("Content-Length", [])
        if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0])):
            raise ValueError("ambiguous content length")
        expected_size = int(lengths[0]) if lengths else None
        if expected_size is not None and expected_size > MAX_EXPORT:
            raise ValueError("export exceeds size limit")
        chunks, size, deadline = [], 0, time.monotonic() + 25
        while True:
            if time.monotonic() > deadline:
                raise ValueError("export exceeded time budget")
            chunk = reply.read1(min(65536, MAX_EXPORT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_EXPORT:
                raise ValueError("export exceeds size limit")
        raw = b"".join(chunks)
        if expected_size is not None and len(raw) != expected_size:
            raise ValueError("incomplete HTTP body")
        return raw, {"generation": int(generation[0]),
                     "server_date": reply.headers.get("Date"), "http_status": 200}


def merge(ranges: list[list[int]]) -> list[list[int]]:
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1] + 1:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def holes(ranges: list[list[int]], after: int) -> list[list[int]]:
    result = []
    cursor = after + 1
    for start, end in ranges:
        if start > cursor:
            result.append([cursor, start - 1])
        cursor = max(cursor, end + 1)
    return result


def inspect(raw: bytes, config: dict) -> tuple[list[list[int]], list, dict]:
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete JSONL record")
    seqs, receipts = [], []
    counts = {"signed_valid": 0, "unsigned": 0, "invalid_signature": 0,
              "referee_payload_unrecognized": 0}
    previous = 0
    for line in raw.splitlines():
        row = decode(line)
        if not isinstance(row, dict) or set(row) not in (
                verifier.SIGNED_KEYS, verifier.UNSIGNED_KEYS):
            raise ValueError("invalid export record shape")
        seq = row["seq"]
        if type(seq) is not int or not previous < seq <= verifier.MAX_SAFE_INTEGER:
            raise ValueError("invalid or reordered sequence")
        previous = seq
        if not all(isinstance(row[k], str) for k in ("from", "ts", "text")):
            raise ValueError("invalid record metadata")
        if seq > config["after"]:
            seqs.append([seq, seq])
        if "sig" not in row:
            counts["unsigned"] += 1
            continue
        try:
            verifier.verify_signed(config["room"], row)
        except (ValueError, KeyError):
            counts["invalid_signature"] += 1
            continue
        counts["signed_valid"] += 1
        if row["from"] != config["referee"]:
            continue
        try:
            payload = decode(row["text"].encode())
            if not isinstance(payload, dict) or payload.get("contest_id") != config["contest_id"]:
                continue
            if payload.get("type") == "sonnet.receipt.v1":
                items = [payload]
            elif payload.get("type") == "sonnet.receipts.v1":
                items = payload["receipts"]
                if not isinstance(items, list):
                    raise ValueError("invalid receipt batch")
            else:
                continue
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("invalid receipt item")
                names = [item[k] for k in ("sender_did", "participant_did") if k in item]
                if item.get("contest_id", config["contest_id"]) != config["contest_id"]:
                    continue
                if (item.get("request_id") != config["request_id"] or not names
                        or any(name != config["participant"] for name in names)):
                    continue
                # Batch-wide disposition is signed together with each item.
                status = item.get("status", payload.get("status"))
                if status not in ("accepted", "rejected"):
                    continue
                receipts.append({"seq": seq, "status": status,
                                 "signed_record": row})
        except (ValueError, KeyError, TypeError):
            counts["referee_payload_unrecognized"] += 1
    return merge(seqs), receipts, counts


def record(root: Path, config: dict, fetcher=fetch, *, budget=MAX_STORAGE) -> dict:
    # Only this new archive is writable. No live identity or mailbox state is read.
    root = root.absolute()
    if root.resolve() != root:
        raise ValueError("archive path must not contain symlinks or dot components")
    root.mkdir(mode=0o700, exist_ok=True)
    private(root, True)
    lockfd = os.open(root / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lockfd, "rb") as lock:
        private(root / ".lock", False)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        used = storage_size(root)
        if any(p.name != ".lock" and not SNAPSHOT.fullmatch(p.name)
               and not re.fullmatch(r"\.pending-[0-9a-f]{32}", p.name)
               for p in root.iterdir()):
            raise ValueError("archive directory contains unrelated files")
        snapshots = sorted(p for p in root.iterdir() if SNAPSHOT.fullmatch(p.name))
        if len(snapshots) >= MAX_SNAPSHOTS or used >= budget:
            raise ValueError("archive storage limit reached; no evidence deleted")
        previous_hash, coverage = None, []
        for number, snapshot in enumerate(snapshots, 1):
            if not snapshot.name.startswith(f"snapshot-{number:06d}-"):
                raise ValueError("archive chain has a missing snapshot")
            meta_raw = (snapshot / "manifest.json").read_bytes()
            meta = decode(meta_raw)
            if meta["previous_manifest_sha256"] != previous_hash or meta["config"] != config:
                raise ValueError("archive chain or configuration mismatch")
            for name, expected in meta["artifacts"].items():
                if name not in ("export.jsonl", "transport.json", "receipts.json"):
                    raise ValueError("invalid archive artifact name")
                if digest((snapshot / name).read_bytes()) != expected:
                    raise ValueError("archive artifact hash mismatch")
            if set(meta["artifacts"]) != {"export.jsonl", "transport.json", "receipts.json"}:
                raise ValueError("archive artifact missing")
            previous_hash = digest(meta_raw)
            coverage = meta["coverage"]
        raw, transport = fetcher(config["room"])
        if len(raw) > MAX_EXPORT or type(transport.get("generation")) is not int:
            raise ValueError("invalid capture size or generation")
        if not 0 <= transport["generation"] <= verifier.MAX_SAFE_INTEGER:
            raise ValueError("invalid generation")
        warnings, receipts, counts = [], [], {}
        new_coverage = coverage
        try:
            observed, receipts, counts = inspect(raw, config)
            if transport["generation"] != config["generation"]:
                warnings.append("generation_mismatch")
                receipts = []  # Room-bound signatures do not bind the generation.
            else:
                if coverage and (not observed or observed[-1][1] < coverage[-1][1]):
                    warnings.append("empty_or_regressed_window")
                new_coverage = merge(coverage + observed)
            if counts["invalid_signature"]:
                warnings.append("invalid_signatures_present")
            if counts["referee_payload_unrecognized"]:
                warnings.append("unrecognized_referee_payload")
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            warnings.append("invalid_export")
            receipts = []
        gaps = holes(new_coverage, config["after"])
        if gaps:
            warnings.append("coverage_gap")
        artifacts = {"export.jsonl": raw, "transport.json": encode(transport),
                     "receipts.json": encode(receipts)}
        meta = {"schema_version": 1, "config": config,
                "captured_at_local": dt.datetime.now(dt.timezone.utc).isoformat(),
                "previous_manifest_sha256": previous_hash,
                "artifacts": {k: digest(v) for k, v in artifacts.items()},
                "coverage": new_coverage, "missing_ranges": gaps,
                "warnings": warnings, "counts": counts,
                "matching_receipts": len(receipts)}
        artifacts["manifest.json"] = encode(meta)
        if used + sum(map(len, artifacts.values())) > budget:
            raise ValueError("archive storage limit reached; no evidence deleted")
        token = uuid.uuid4().hex
        staging = root / (".pending-" + token)
        staging.mkdir(mode=0o700)
        for name, data in artifacts.items():
            write_new(staging / name, data)
        sync_dir(staging)
        final = root / f"snapshot-{len(snapshots)+1:06d}-{token}"
        os.rename(staging, final)
        sync_dir(root)
        return {"snapshot": final.name, "warnings": warnings,
                "missing_ranges": gaps, "matching_receipts": len(receipts),
                "coverage": new_coverage}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--after", type=int, required=True)
    parser.add_argument("--contest-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--referee", required=True)
    args = parser.parse_args()
    config = vars(args).copy()
    root = config.pop("directory")
    try:
        if not verifier.ROOM.fullmatch(args.room):
            raise ValueError("invalid room")
        if not all(verifier.DID.fullmatch(d) for d in (args.participant, args.referee)):
            raise ValueError("invalid DID")
        if not all(0 <= n <= verifier.MAX_SAFE_INTEGER for n in (args.generation, args.after)):
            raise ValueError("invalid generation or starting sequence")
        if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", s)
                   for s in (args.contest_id, args.request_id)):
            raise ValueError("invalid contest or request identifier")
        result = record(root, config)
        print(json.dumps(result, sort_keys=True))
        return 2 if result["warnings"] else 0
    except Exception as error:
        # Do not echo server text, URLs, private room names, or parser excerpts.
        print(f"ERROR: capture failed ({type(error).__name__}); inspect archive before retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
