#!/usr/bin/env bash
# FASE 0.5 — CUTOVER: pindahkan tim ForcAD dari container ke VM.
#
# Sebelum:  teams[].ip = team1-svc / team2-svc   (container di bridge docker)
# Sesudah:  teams[].ip = 10.13.37.11 / .12       (VM di network adnet)
#           nama tim   = Cyb0x1 Athena / Cyb0x1 Ares
#
# Checker sengaja MASIH example bawaan ForcAD. Kalau setelah cutover checker
# tetap UP, artinya topologi VM benar — sehingga kalau nanti Fase 1 gagal,
# penyebabnya pasti adapter, bukan jaringan.
#
# Syarat: deploy/fase05-gate.sh sudah LOLOS.
# PERINGATAN: menjalankan `control.py reset` — database game DIHAPUS.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

FORCAD=$HOME/adlab/forcad
PY=$FORCAD/.venv/bin/python
SRC=$FORCAD/tests/service
PORT=10000
VMS=("athena|10.13.37.11" "ares|10.13.37.12")
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# ------------------------------------------- 1. example service ke dalam VM ---
say "Memasang example service ke dalam tiap VM"
for entry in "${VMS[@]}"; do
  IFS='|' read -r NAME IP <<< "$entry"
  echo "-- $NAME ($IP)"
  # tar over ssh: VM cloud image belum tentu punya rsync
  tar czf - -C "$(dirname "$SRC")" "$(basename "$SRC")" \
    | $SSH "reky@$IP" 'mkdir -p /opt/adlab && tar xzf - -C /opt/adlab'
  $SSH "reky@$IP" "
    docker rm -f gate-probe >/dev/null 2>&1 || true
    cd /opt/adlab/service
    docker build -q -t adlab-example . >/dev/null
    docker rm -f example >/dev/null 2>&1 || true
    docker run -d --name example -p $PORT:$PORT --restart unless-stopped adlab-example >/dev/null
    sleep 2
    docker ps --format '{{.Names}} {{.Status}}' | head -2
  "
done

say "Uji service dari host"
for entry in "${VMS[@]}"; do
  IFS='|' read -r NAME IP <<< "$entry"
  printf '  %-8s ' "$NAME"
  curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" "http://$IP:$PORT/ping/" || echo GAGAL
done

# ----------------------------------------------------- 2. tukar config.yml ---
say "Menukar config.yml ke IP VM + nama tim"
cp "$FORCAD/config.yml" "$FORCAD/config.pre-cutover.yml"
cp "$HOME/adlab/config.fase05.yml" "$FORCAD/config.yml"
cd "$FORCAD"
$PY control.py validate

# ------------------------------------------------------ 3. reset & start ---
say "Reset game (database dihapus) lalu start ulang"
# ForcAD menyimpan data postgres di DIREKTORI HOST (docker_volumes/), bukan
# named volume — `docker volume ls` kosong. Jadi `reset` (yang cuma `down -v`)
# TIDAK menghapusnya, sementara `setup` membangkitkan password baru setiap
# dipanggil. Akibatnya:
#   FATAL: password authentication failed for user "forcad"
#   initializer stuck "Waiting for postgres & rabbitmq", nginx balas 502.
#
# `control.py clean` seharusnya menghapus direktori itu, TAPI GAGAL DIAM-DIAM:
# isinya milik root (postgres di container menulis sebagai root) sedangkan
# clean berjalan sebagai reky. Postgres lalu bilang
#   "Database directory appears to contain a database; Skipping initialization"
# dan memakai password lama. Karena itu dihapus paksa dengan sudo di sini.
$PY control.py reset
$PY control.py clean || true
sudo rm -rf "$FORCAD/docker_volumes"
$PY control.py setup
$PY control.py start --fast

say "Selesai. Verifikasi:"
echo "  curl -s http://192.168.43.136:8080/api/client/teams/"
echo "  docker compose -f docker-compose-base.yml -f docker-compose-fast.yml logs --tail=20 celery | grep Verdicts"
