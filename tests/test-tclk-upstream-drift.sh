#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'find "$TEST_DIR" -depth -delete' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

mkdir "$TEST_DIR/bin"
REVIEWED_COMMIT="$(sed -n 's/^REVIEWED_COMMIT="\([0-9a-f]\{40\}\)"/\1/p' \
  "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh")"
REVIEWED_SHA256="$(sed -n 's/^REVIEWED_SHA256="\([0-9a-f]\{64\}\)"/\1/p' \
  "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh")"
[ -n "$REVIEWED_COMMIT" ] && [ -n "$REVIEWED_SHA256" ] || fail "reviewed constants missing"
export REVIEWED_COMMIT REVIEWED_SHA256

cat >"$TEST_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
case "${!#}" in
  *api.github.com*)
    if [ "${DRIFT_COMMIT:-0}" = 1 ]; then
      printf '{"sha":"%040d"}\n' 0
    else
      printf '{"sha":"%s"}\n' "$REVIEWED_COMMIT"
    fi ;;
  *raw.githubusercontent.com*) printf 'reviewed fixture\\n' ;;
  *) exit 22 ;;
esac
EOF
cat >"$TEST_DIR/bin/sha256sum" <<'EOF'
#!/usr/bin/env bash
if [ "${DRIFT:-0}" = 1 ]; then
  printf '%064d  %s\n' 0 "$1"
else
  printf '%s  %s\n' "$REVIEWED_SHA256" "$1"
fi
EOF
chmod 755 "$TEST_DIR/bin/curl" "$TEST_DIR/bin/sha256sum"

BEFORE="$(sha256sum "$ROOT_DIR/tests/test-tclk-golden-vectors.py")"
PATH="$TEST_DIR/bin:$PATH" "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh" \
  >"$TEST_DIR/pass.out"
grep -Eq 'still match the reviewed constants' "$TEST_DIR/pass.out" ||
  fail "matching fixture did not pass"
pass "matching upstream commit and hash accepted"

if PATH="$TEST_DIR/bin:$PATH" DRIFT_COMMIT=1 \
  "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh" >"$TEST_DIR/commit-drift.out" 2>&1; then
    fail "commit drift was accepted"
fi
grep -Eq 'commit drifted' "$TEST_DIR/commit-drift.out" || fail "commit drift was not reported"
pass "commit drift failed closed"

if PATH="$TEST_DIR/bin:$PATH" DRIFT=1 \
  "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh" >"$TEST_DIR/drift.out" 2>&1; then
    fail "content drift was accepted"
fi
grep -Eq 'content drifted' "$TEST_DIR/drift.out" || fail "content drift was not reported"
[ "$(sha256sum "$ROOT_DIR/tests/test-tclk-golden-vectors.py")" = "$BEFORE" ] ||
  fail "drift check rewrote the reviewed constants"
pass "content drift failed without rewriting reviewed constants"

if grep -En 'sed -i|perl -i|apply_patch|git (add|commit|push)' \
  "$ROOT_DIR/scripts/check-tclk-upstream-drift.sh" >/dev/null; then
    fail "drift checker contains an automatic rewrite or publication path"
fi
pass "drift checker has no automatic rewrite or publication path"

echo "All tclk upstream-drift checks passed."
