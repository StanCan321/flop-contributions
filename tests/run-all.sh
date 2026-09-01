#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

cd "$ROOT_DIR"

./tests/test-sender-static.sh
./tests/test-ack-mailbox.sh
./tests/test-poll-state.sh
./tests/test-poll-backoff.sh
./tests/test-envelope-verifier.sh

echo "All network-free checks passed."
