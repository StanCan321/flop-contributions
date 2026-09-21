#!/usr/bin/env bash
set -euo pipefail

EXPECTED_VERSION="${1:-0.14.0}"
PUBLIC_ROOM="${2:-}"
BASE_URL="https://technocore.chat"
MAX_BYTES=33554432
PROBE_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$PROBE_DIR"
}

trap cleanup EXIT

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

fetch() {
    local encoding="$1"
    local url="$2"
    local name="$3"
    local -a decode=()

    if [ "$encoding" != "identity" ]; then
        decode=(--compressed)
    fi

    curl \
        --proto '=https' \
        --tlsv1.2 \
        --connect-timeout 10 \
        --max-time 45 \
        --max-filesize "$MAX_BYTES" \
        -fsS \
        "${decode[@]}" \
        -H "Accept-Encoding: $encoding" \
        -D "$PROBE_DIR/$name.headers" \
        -o "$PROBE_DIR/$name.body" \
        "$url"
}

header_value() {
    local name="$1"
    local header="$2"
    awk -v wanted="$header" '
        BEGIN { IGNORECASE = 1 }
        {
            sub("\r$", "")
            split($0, parts, ":")
            if (tolower(parts[1]) == tolower(wanted)) {
                sub(/^[^:]*:[[:space:]]*/, "")
                value = tolower($0)
            }
        }
        END { print value }
    ' "$PROBE_DIR/$name.headers"
}

fetch identity "$BASE_URL/config" config

SERVICE_VERSION="$(jq -er '.version | select(type == "string")' "$PROBE_DIR/config.body")" ||
    fail "service config did not contain a string version"

if [ "$SERVICE_VERSION" != "$EXPECTED_VERSION" ]; then
    echo "STOP: expected Technocore $EXPECTED_VERSION, observed $SERVICE_VERSION" >&2
    exit 3
fi

probe_resource() {
    local label="$1"
    local url="$2"

    fetch identity "$url" "$label.identity"
    fetch gzip "$url" "$label.gzip"
    fetch br "$url" "$label.br"

    local identity_sha gzip_sha br_sha
    identity_sha="$(sha256sum "$PROBE_DIR/$label.identity.body" | awk '{print $1}')"
    gzip_sha="$(sha256sum "$PROBE_DIR/$label.gzip.body" | awk '{print $1}')"
    br_sha="$(sha256sum "$PROBE_DIR/$label.br.body" | awk '{print $1}')"

    [ "$identity_sha" = "$gzip_sha" ] ||
        fail "$label gzip decoded bytes differ from identity"
    [ "$identity_sha" = "$br_sha" ] ||
        fail "$label Brotli decoded bytes differ from identity"

    local identity_encoding gzip_encoding br_encoding vary
    identity_encoding="$(header_value "$label.identity" content-encoding)"
    gzip_encoding="$(header_value "$label.gzip" content-encoding)"
    br_encoding="$(header_value "$label.br" content-encoding)"
    vary="$(header_value "$label.br" vary)"

    { [ -z "$identity_encoding" ] || [ "$identity_encoding" = "identity" ]; } ||
        fail "$label identity request returned $identity_encoding"
    [ "$gzip_encoding" = "gzip" ] ||
        fail "$label gzip request returned ${gzip_encoding:-no content encoding}"
    [ "$br_encoding" = "br" ] ||
        fail "$label Brotli request returned ${br_encoding:-no content encoding}"
    [[ "$vary" == *"accept-encoding"* ]] ||
        fail "$label response does not vary on Accept-Encoding"

    jq -n \
        --arg resource "$label" \
        --arg sha256 "$identity_sha" \
        --argjson bytes "$(wc -c <"$PROBE_DIR/$label.identity.body")" \
        '{resource: $resource, decoded_sha256: $sha256, decoded_bytes: $bytes}'
}

read_last_seq() {
    local response="$1"

    jq -er '
        .last_seq
        | select(type == "number")
        | select(floor == .)
        | select(. >= 0 and . <= 9007199254740991)
    ' "$response"
}

validate_export_snapshot() {
    local encoding="$1"
    local body="$2"
    local pre_export_last_seq="$3"
    local exported_last_seq

    if ! exported_last_seq="$(python3 - "$body" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()

if not data:
    raise SystemExit("export body is empty")
if not data.endswith(b"\n"):
    raise SystemExit("export body does not end with a newline")

def reject_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value

last_seq = -1
for line_number, line in enumerate(data.splitlines(), start=1):
    if not line:
        raise SystemExit(f"empty JSONL line at {line_number}")
    try:
        record = json.loads(line, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid JSONL at line {line_number}: {exc}") from exc
    if not isinstance(record, dict):
        raise SystemExit(f"JSONL line {line_number} is not an object")
    seq = record.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise SystemExit(f"JSONL line {line_number} has an invalid seq")
    if seq < 0 or seq > 9007199254740991:
        raise SystemExit(f"JSONL line {line_number} has an unsafe seq")
    if seq <= last_seq:
        raise SystemExit(f"JSONL seq is not strictly increasing at line {line_number}")
    last_seq = seq

print(last_seq)
PY
)"; then
        fail "export $encoding response is not a complete JSONL snapshot"
    fi

    [ "$exported_last_seq" -ge "$pre_export_last_seq" ] ||
        fail "export $encoding ends at seq $exported_last_seq before pre-export head $pre_export_last_seq"
}

probe_export() {
    local room="$1"
    local room_url="$BASE_URL/r/$room"
    local pre_export_last_seq

    fetch identity "$room_url?format=json&limit=1" export.head
    pre_export_last_seq="$(read_last_seq "$PROBE_DIR/export.head.body")" ||
        fail "room head did not contain a safe last_seq"

    probe_resource export "$room_url/export"

    for encoding in identity gzip br; do
        validate_export_snapshot \
            "$encoding" \
            "$PROBE_DIR/export.$encoding.body" \
            "$pre_export_last_seq"
    done

    printf 'Export completeness: each decoded snapshot reaches pre-export last_seq %s.\n' \
        "$pre_export_last_seq"
}

if [ -n "$PUBLIC_ROOM" ] && [[ ! "$PUBLIC_ROOM" =~ ^[a-z0-9][a-z0-9_-]{0,47}$ ]]; then
    fail "public room must match the Technocore room-name grammar"
fi

echo "Technocore compression compatibility probe"
echo "Service version: $SERVICE_VERSION"
echo "Read-only requests only; response bodies are deleted on exit."
probe_resource docs "$BASE_URL/llms.txt"

if [ -n "$PUBLIC_ROOM" ]; then
    probe_export "$PUBLIC_ROOM"
else
    echo "Export check skipped: pass a reviewed public room as argument 2."
fi
