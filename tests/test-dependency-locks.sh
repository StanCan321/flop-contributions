#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

pass() {
    echo "PASS: $*"
}

python3 - "$ROOT_DIR" <<'PY' || exit 1
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = {
    "uv.txt": {"uv": "0.12.5"},
    "verifier.txt": {
        "cffi": "2.1.1",
        "cryptography": "50.0.1",
        "pycparser": "3.0",
    },
}

for filename, packages in expected.items():
    path = root / "requirements" / filename
    text = path.read_text(encoding="utf-8")
    if "--index-url" in text or "--extra-index-url" in text or " @ " in text:
        raise SystemExit(f"{filename}: unreviewed package source")

    logical = []
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        current += (" " if current else "") + line.removesuffix("\\").strip()
        if not line.endswith("\\"):
            logical.append(current)
            current = ""
    if current:
        raise SystemExit(f"{filename}: unterminated continuation")

    found = {}
    for requirement in logical:
        match = re.match(r"^([A-Za-z0-9_.-]+)==([0-9.]+)(?:\s*;[^-]+)?\s+", requirement)
        if not match:
            raise SystemExit(f"{filename}: invalid pinned requirement")
        name, version = match.groups()
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)", requirement)
        if not hashes:
            raise SystemExit(f"{filename}: {name} has no SHA-256 hashes")
        if len(hashes) != len(set(hashes)):
            raise SystemExit(f"{filename}: {name} repeats a hash")
        found[name] = version

    if found != packages:
        raise SystemExit(f"{filename}: package closure changed: {found!r}")
PY
pass "universal dependency locks are complete and hash-pinned"

WORKFLOW="$ROOT_DIR/.github/workflows/network-free-tests.yml"
grep -Fq -- '--require-hashes' "$WORKFLOW" || fail "CI does not require hashes"
grep -Fq -- '-r requirements/uv.txt' "$WORKFLOW" || fail "CI does not use the uv lock"
grep -Fq -- '-r requirements/verifier.txt' "$WORKFLOW" ||
    fail "CI does not use the verifier lock"
pass "CI installs only from reviewed hash locks"

for script in send.sh review-mailbox.sh ack-reviewed-mailbox.sh; do
    grep -Fq 'UV_OFFLINE=1 uv run' "$ROOT_DIR/scripts/$script" ||
        fail "$script does not force offline dependency execution"
    grep -Fq 'requirements-verifier.txt' "$ROOT_DIR/scripts/$script" ||
        fail "$script does not require the installed verifier lock"
done
pass "operational cryptography runs are offline and lock-gated"

echo "All dependency-lock checks passed."
