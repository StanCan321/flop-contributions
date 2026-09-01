#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

AGENT_DIR="${1:-$HOME/technocore-agent}"
SOURCE_LOCK="$ROOT_DIR/requirements/verifier.txt"
INSTALLED_LOCK="$AGENT_DIR/requirements-verifier.txt"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -d "$AGENT_DIR" ] || fail "agent directory is missing: $AGENT_DIR"
[ ! -L "$AGENT_DIR" ] || fail "agent directory must not be a symbolic link"
[ -f "$SOURCE_LOCK" ] || fail "verifier dependency lock is missing"
[ ! -L "$SOURCE_LOCK" ] || fail "verifier dependency lock must not be a symbolic link"
command -v uv >/dev/null || fail "uv is not installed"

install -m 600 "$SOURCE_LOCK" "$INSTALLED_LOCK"

TEMP_ENV="$(mktemp -d "$AGENT_DIR/.dependency-check.XXXXXX")"
cleanup() {
    find "$TEMP_ENV" -depth -delete
}
trap cleanup EXIT

uv python install 3.12
uv venv --python 3.12 "$TEMP_ENV/venv"
uv pip install \
  --python "$TEMP_ENV/venv/bin/python" \
  --require-hashes \
  -r "$INSTALLED_LOCK"

"$TEMP_ENV/venv/bin/python" - <<'PY'
import cffi
import cryptography
import pycparser

assert cryptography.__version__ == "50.0.1"
assert cffi.__version__ == "2.1.1"
assert pycparser.__version__ == "3.00"
PY

UV_OFFLINE=1 uv run \
  --python 3.12 \
  --with-requirements "$INSTALLED_LOCK" \
  python -c 'import cryptography; assert cryptography.__version__ == "50.0.1"'

echo "Hash-locked dependencies prepared for offline operation."
