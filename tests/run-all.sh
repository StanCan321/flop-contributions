#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

cd "$ROOT_DIR"

./tests/test-sender-static.sh
./tests/test-sender-dynamic.sh
./tests/test-ack-mailbox.sh
./tests/test-poll-state.sh
./tests/test-poll-backoff.sh
./tests/test-envelope-verifier.sh
./tests/test-local-integration.sh
./tests/test-trusted-consumer.sh
./tests/test-installation-verifier.sh
./tests/test-dependency-locks.sh
./tests/test-tclk-transcript.sh
./tests/test-tclk-review-wrapper.sh
uv run --python 3.12 --with-requirements requirements/verifier.txt \
  tests/test-tclk-golden-vectors.py
uv run --python 3.12 --with-requirements requirements/verifier.txt \
  tests/test-tclk-parser-properties.py
./tests/test-tclk-upstream-drift.sh
uv run --python 3.12 --with-requirements requirements/verifier.txt \
  tests/test-tclk-paper-rail.py

echo "All network-free checks passed."
