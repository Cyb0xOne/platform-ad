#!/usr/bin/env bash
# CUTOVER dashboard — bangun image React+legacy, jalankan dua listener, smoke.
#
# Dijalankan DI SERVER (akses LAN + Docker + secrets). Idempotent & rollback-safe.
#   (tanpa flag) : UI legacy tetap di `/`, React di /next/, admin loopback 8091.
#   --react      : pindahkan `/` ke React. Rollback: jalankan lagi tanpa flag.
#
# TIDAK merotasi token (operasi ForcAD ireversibel & spesifik engine) dan TIDAK
# menyentuh database game — langkah itu tetap manual (lihat akhir skrip +
# docs/RUNBOOK-cutover.md). Deploy git-driven: `git pull` dulu di server.
#
# Prasyarat (dicek fail-fast): .env (FORCAD_DSN), secrets/vmkey, secrets/controlkey,
# wrapper forced-command terpasang di host, network forcad_default sudah ada.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

DASHBOARD_DIR=${DASHBOARD_DIR:-$HOME/adlab/dashboard}
WRAPPER=${FORCAD_CONTROL_WRAPPER:-$HOME/adlab/control-host/forcad-control.sh}
WANT_REACT=0
[[ "${1:-}" == "--react" ]] && WANT_REACT=1

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mGAGAL: %s\033[0m\n' "$*" >&2; exit 1; }

cd "$DASHBOARD_DIR" || die "dir dashboard tidak ada: $DASHBOARD_DIR"

# ------------------------------------------------------- 1. prasyarat ---
say "Cek prasyarat"
[[ -f .env ]]                || die ".env tidak ada (butuh FORCAD_DSN)"
grep -q '^FORCAD_DSN=' .env  || die ".env tidak memuat FORCAD_DSN"
[[ -r secrets/vmkey ]]       || die "secrets/vmkey tidak ada (SSH ke vulnbox)"
[[ -r secrets/controlkey ]] || die "secrets/controlkey tidak ada (kontrol ForcAD)"
[[ -x "$WRAPPER" ]]          || die "wrapper forced-command belum terpasang: $WRAPPER"
docker network inspect forcad_default >/dev/null 2>&1 \
  || die "network forcad_default tidak ada (ForcAD belum jalan?)"
mkdir -p admin-data
echo "  OK"

# --------------------------------------------------- 2. opsi default UI ---
say "Atur default UI"
sed -i '/^DASHBOARD_DEFAULT_UI=/d' .env
if [[ $WANT_REACT -eq 1 ]]; then
  echo 'DASHBOARD_DEFAULT_UI=react' >> .env
  echo "  / -> React (rollback: jalankan skrip tanpa --react, atau akses /legacy/)"
else
  echo "  / -> legacy (default, rollback-safe). React tetap di /next/."
fi

# ------------------------------------------------------- 3. build & up ---
say "Build image multi-stage + jalankan dua listener"
docker compose build
docker compose up -d

# ------------------------------------------------------------ 4. smoke ---
say "Smoke test isolasi rute (tunggu listener siap)"
sleep 4
smoke() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$1" 2>/dev/null || echo 000; }
PUB=http://127.0.0.1:8090
ADM=http://127.0.0.1:8091
printf '  public  /        -> %s (harap 200)\n' "$(smoke $PUB/)"
printf '  public  /next/   -> %s (harap 200)\n' "$(smoke $PUB/next/)"
printf '  public  /admin/  -> %s (harap 404)\n' "$(smoke $PUB/admin/)"
printf '  admin   /admin/  -> %s (harap 200)\n' "$(smoke $ADM/admin/)"
printf '  admin   /next/   -> %s (harap 404)\n' "$(smoke $ADM/next/)"

say "Status container"
docker compose ps || true

# ------------------------------------------------ 5. langkah manual sisa ---
say "SELESAI (deploy + smoke). Langkah IREVERSIBEL yang HARUS manual:"
cat <<'EOF'
  1) ROTASI TOKEN TIM — token sempat terekspos di scoreboard publik pra-Fase-0.
     Rotasi lewat jalur resmi ForcAD, dalam maintenance window, lalu bagikan
     token baru. TIDAK diotomasi di sini (ireversibel + spesifik engine).
  2) Verifikasi scoreboard publik tidak lagi menampilkan token apa pun.
  3) Rehearsal lifecycle via admin (SSH tunnel dari mesin operator):
       ssh -L 8091:127.0.0.1:8091 reky@192.168.43.136
       buka http://127.0.0.1:8091/admin/  ->  pause  ->  resume  (ronde uji)
  Detail lengkap & rollback: docs/RUNBOOK-cutover.md
EOF
