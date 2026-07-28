#!/usr/bin/env bash
# Bukti isolasi tag:ad-player — node Tailscale bertag sekali pakai di container.
#
# Menguji DUA arah sekaligus, karena policy yang "kelihatan benar" bukan bukti:
#   HARUS BISA    : subnet lab 10.13.37.0/24
#   HARUS DITOLAK : device lingkungan utama (router, laptop/hp reky & dandy)
#
# Pakai:  ./verify-ad-player-isolation.sh tskey-auth-xxxxx
# Container dihapus otomatis saat selesai, jadi tidak meninggalkan jejak di tailnet
# selain node yang langsung di-logout.
set -uo pipefail

KEY="${1:-}"
[ -z "$KEY" ] && { echo "usage: $0 <tskey-auth-...>"; exit 2; }

NAME="ad-player-probe-$$"
LAB_OK=(10.13.37.11:1337 10.13.37.12:1337)          # harus tembus
MAIN_DENY=(100.87.29.122:22 100.65.243.55:22 100.83.173.52:22 100.71.84.24:22)  # harus buntu

cleanup() {
  docker exec "$NAME" tailscale logout >/dev/null 2>&1 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== menjalankan node bertag sekali pakai =="
docker run -d --name "$NAME" --rm \
  --cap-add NET_ADMIN --device /dev/net/tun \
  -e TS_AUTHKEY="$KEY" -e TS_ACCEPT_DNS=false \
  -e TS_EXTRA_ARGS="--accept-routes --hostname=$NAME" \
  tailscale/tailscale:latest >/dev/null || { echo "gagal start container"; exit 1; }

for i in $(seq 30); do
  docker exec "$NAME" tailscale status >/dev/null 2>&1 && break
  sleep 2
done

echo "== identitas node (harus tagged, BUKAN milik user) =="
docker exec "$NAME" tailscale status --json 2>/dev/null \
  | python3 -c 'import sys,json; s=json.load(sys.stdin).get("Self",{}); print("   tags:", s.get("Tags") or "TIDAK ADA -> policy belum berlaku!")'

probe() { docker exec "$NAME" timeout 6 nc -z -w4 "${1%%:*}" "${1##*:}" >/dev/null 2>&1; }

fail=0
echo "== A. akses ke subnet lab (harus BISA) =="
for t in "${LAB_OK[@]}"; do
  if probe "$t"; then echo "   OK    $t tembus"; else echo "   GAGAL $t buntu (seharusnya bisa)"; fail=1; fi
done

echo "== B. akses ke lingkungan utama (harus DITOLAK) =="
for t in "${MAIN_DENY[@]}"; do
  if probe "$t"; then echo "   BOCOR $t tembus (seharusnya ditolak!)"; fail=1; else echo "   OK    $t diblokir"; fi
done

echo
[ "$fail" -eq 0 ] && echo "HASIL: isolasi TERBUKTI" || echo "HASIL: ADA MASALAH — jangan bagikan auth key dulu"
exit "$fail"
