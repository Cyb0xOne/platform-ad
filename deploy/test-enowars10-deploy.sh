#!/usr/bin/env bash
# Offline lock untuk fix bug override-null di enowars10-deploy.sh (Task 5).
# `docker` di-stub sebagai fungsi bash yang di-export: fungsi menang atas lookup
# PATH walau skrip me-reset PATH sendiri. $HOME diarahkan ke dir sementara supaya
# WORK=$HOME/adlab/eno10/<svc> jatuh di sandbox. Tanpa framework; assert murni.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY="$DIR/enowars10-deploy.sh"
FAILS=0

docker() {
  if [ "${1:-}" = compose ]; then
    shift
    case "${1:-}" in
      config) [ -n "${FAKE_SERVICES:-}" ] && printf '%s\n' $FAKE_SERVICES; return 0 ;;
      *) return 0 ;;
    esac
  fi
  return 0
}
export -f docker

LAST_OUT=""; LAST_RC=0; LAST_OVR=""
run_case() {
  local svc=testsvc home
  home="$(mktemp -d)"
  mkdir -p "$home/adlab/eno10/$svc"
  echo "services: {}" > "$home/adlab/eno10/$svc/docker-compose.yml"
  [ -n "${PRESEED:-}" ] && printf '%s' "$PRESEED" > "$home/adlab/eno10/$svc/docker-compose.override.yml"
  LAST_OUT="$(HOME="$home" FAKE_SERVICES="${FAKE_SERVICES:-}" bash "$DEPLOY" "$svc" up 2>&1)"
  LAST_RC=$?
  LAST_OVR="$home/adlab/eno10/$svc/docker-compose.override.yml"
}
ok()  { echo "  ok: $1"; }
bad() { echo "  FAIL: $1"; FAILS=$((FAILS+1)); }

echo "case A: daftar service kosong -> exit!=0, override TIDAK ditulis"
FAKE_SERVICES="" PRESEED="" run_case
{ [ "$LAST_RC" -ne 0 ] && ok "exit non-zero ($LAST_RC)"; } || bad "harus exit non-zero, dapat 0"
{ [ ! -f "$LAST_OVR" ] && ok "tak ada override"; } || bad "override seharusnya tak dibuat"
echo "$LAST_OUT" | grep -q FATAL && ok "pesan FATAL ada" || bad "pesan FATAL hilang"

echo "case B: service ada -> exit 0, override benar"
FAKE_SERVICES="app db" PRESEED="" run_case
{ [ "$LAST_RC" -eq 0 ] && ok "exit 0"; } || bad "harus exit 0, dapat $LAST_RC"
grep -qE "^  app:" "$LAST_OVR" && ok "app: ada" || bad "app: hilang"
grep -qE "^  db:"  "$LAST_OVR" && ok "db: ada"  || bad "db: hilang"
grep -qE "^  forcad_default:" "$LAST_OVR" && ok "network forcad_default" || bad "forcad_default hilang"
grep -qE "external: true" "$LAST_OVR" && ok "external: true" || bad "flag external hilang"

echo "case C: override rusak sudah ada -> di-heal (rm sebelum regen)"
FAKE_SERVICES="app" PRESEED=$'services:\n' run_case
{ [ "$LAST_RC" -eq 0 ] && ok "exit 0"; } || bad "harus exit 0, dapat $LAST_RC"
grep -qE "^  app:" "$LAST_OVR" && ok "healed: app: ada" || bad "override tak diregenerasi"

echo
{ [ "$FAILS" -eq 0 ] && { echo "ALL PASS"; exit 0; }; } || { echo "$FAILS KEGAGALAN"; exit 1; }
