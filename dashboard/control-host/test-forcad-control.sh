#!/bin/bash
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$DIR/forcad-control.sh"
TMP="$(mktemp -d)"
FORCAD="$TMP/forcad"
TEST_HOME="$TMP/home"
ARGV_LOG="$TMP/argv.log"
STDOUT_FILE="$TMP/stdout"
STDERR_FILE="$TMP/stderr"
EXPECTED_STDERR="$TMP/expected-stderr"
HOLDER_PID=""
FAILS=0
LAST_RC=0

cleanup() {
  if [ -n "$HOLDER_PID" ]; then
    kill "$HOLDER_PID" 2>/dev/null || true
    wait "$HOLDER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

mkdir -p "$FORCAD" "$TEST_HOME"
PYTHON="$(command -v python3)"

cat > "$FORCAD/control.py" <<'PY'
import json
import os
import sys

with open(os.environ["FAKE_ARGV_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:], separators=(",", ":")) + "\n")

sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))
PY

ok() {
  printf '  ok: %s\n' "$1"
}

bad() {
  printf '  FAIL: %s\n' "$1"
  FAILS=$((FAILS + 1))
}

run_wrapper() {
  local original="$1"
  local fake_exit="${2:-0}"
  local fake_stderr="${3:-}"

  : > "$ARGV_LOG"
  : > "$STDOUT_FILE"
  : > "$STDERR_FILE"
  SSH_ORIGINAL_COMMAND="$original" \
    HOME="$TEST_HOME" \
    FORCAD_DIR="$FORCAD" \
    FORCAD_PY="$PYTHON" \
    FAKE_ARGV_LOG="$ARGV_LOG" \
    FAKE_EXIT="$fake_exit" \
    FAKE_STDERR="$fake_stderr" \
    "$WRAPPER" >"$STDOUT_FILE" 2>"$STDERR_FILE"
  LAST_RC=$?
}

check_translation() {
  local original="$1"
  local expected="$2"

  run_wrapper "$original"
  [ "$LAST_RC" -eq 0 ] && ok "$original exits 0" || bad "$original exits $LAST_RC, expected 0"
  [ "$(<"$ARGV_LOG")" = "$expected" ] \
    && ok "$original argv is $expected" \
    || bad "$original argv is '$(<"$ARGV_LOG")', expected '$expected'"
}

printf 'translation\n'
check_translation start '["start","--fast"]'
check_translation pause '["pause"]'
check_translation resume '["resume"]'

printf 'rejections\n'
REJECTED=(
  reset
  clean
  setup
  build
  "rd down -v"
  "start; reset"
  "start --fast --build"
  "start "
  START
  ""
  $'start\nreset'
)
for payload in "${REJECTED[@]}"; do
  run_wrapper "$payload"
  printf -v label '%q' "$payload"
  [ "$LAST_RC" -eq 64 ] && ok "$label exits 64" || bad "$label exits $LAST_RC, expected 64"
  [ ! -s "$ARGV_LOG" ] && ok "$label is not invoked" || bad "$label invoked fake control.py"
done

printf 'failure propagation\n'
FAILURE_STDERR=$'fake control failure: unchanged\nsecond line\n'
run_wrapper pause 1 "$FAILURE_STDERR"
printf '%s' "$FAILURE_STDERR" > "$EXPECTED_STDERR"
[ "$LAST_RC" -eq 1 ] && ok "control.py exit 1 propagates" || bad "control.py exit became $LAST_RC, expected 1"
cmp -s "$EXPECTED_STDERR" "$STDERR_FILE" \
  && ok "control.py stderr is unchanged" \
  || bad "control.py stderr changed"

printf 'lock contention\n'
LOCKFILE="$TEST_HOME/.adlab-control.lock"
READY="$TMP/lock-ready"
flock "$LOCKFILE" bash -c 'printf ready > "$1"; sleep 30' bash "$READY" &
HOLDER_PID=$!
for _ in {1..100}; do
  [ -f "$READY" ] && break
  sleep 0.01
done
if [ ! -f "$READY" ]; then
  bad "background flock did not acquire the lock"
else
  run_wrapper resume
  [ "$LAST_RC" -eq 75 ] && ok "lock contention exits 75" || bad "lock contention exits $LAST_RC, expected 75"
  [ ! -s "$ARGV_LOG" ] && ok "lock contention does not invoke control.py" || bad "lock contention invoked control.py"
fi
kill "$HOLDER_PID" 2>/dev/null || true
wait "$HOLDER_PID" 2>/dev/null || true
HOLDER_PID=""

printf '\n'
if [ "$FAILS" -eq 0 ]; then
  printf 'ALL PASS\n'
  exit 0
fi
printf '%s FAILURE(S)\n' "$FAILS"
exit 1
