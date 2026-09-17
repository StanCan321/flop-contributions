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

if [ -n "$PUBLIC_ROOM" ] && [[ ! "$PUBLIC_ROOM" =~ ^[a-z0-9][a-z0-9_-]{0,47}$ ]]; then
    fail "public room must match the Technocore room-name grammar"
fi

echo "Technocore compression compatibility probe"
echo "Service version: $SERVICE_VERSION"
echo "Read-only requests only; response bodies are deleted on exit."
probe_resource docs "$BASE_URL/llms.txt"

if [ -n "$PUBLIC_ROOM" ]; then
    probe_resource export "$BASE_URL/r/$PUBLIC_ROOM/export"
else
    echo "Export check skipped: pass a reviewed public room as argument 2."
fi
