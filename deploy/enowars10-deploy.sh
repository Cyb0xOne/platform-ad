#!/usr/bin/env bash
# deploy/enowars10-deploy.sh — jalankan DI SERVER
# pemakaian: enowars10-deploy.sh <service-dir> [up|down]
#   contoh: enowars10-deploy.sh greple up   -> build+jalankan di host, ditempel ke network forcad_default
#
# CATATAN sumber: bank soal enowars10 ada di LAPTOP, bukan server. Untuk uji,
# rsync source service ke server lebih dulu:
#   rsync -az --rsync-path=/usr/bin/rsync <laptop>/.../shining-arc-team-repo/$SVC/ \
#     reky@<server>:~/adlab/eno10/$SVC/
#
# CATATAN jalur jangkau (dipelajari dari implementasi greple, Task 2):
#   Checker jalan di container `forcad-celery` pada network `forcad_default`.
#   docker-compose.yml bawaan tiap service enowars10 memakai network PROJEK
#   SENDIRI (mis. "greple_service_default") — celery TIDAK otomatis bisa
#   menjangkaunya. Dua opsi disebut di brief: (a) VM tim 10.13.37.x seperti
#   service Fase 1, atau (b) tempel service ke `forcad_default` dan gate
#   pakai IP container-nya di situ. Skrip ini memakai opsi (b) — paling
#   ringan untuk servis HTTP kecil yang tak perlu resource VM.
#
#   Cara tempelnya: skrip membuat docker-compose.override.yml (SEKALI, kalau
#   belum ada) yang menaruh SEMUA service pada compose file ke network
#   `forcad_default` (external) SEKALIGUS mempertahankan network `default`
#   proyek (supaya service multi-container tetap bisa saling bicara secara
#   internal — mis. app + db). Override diregenerasi ULANG tiap run dari daftar
#   service otoritatif (override lama dibuang dulu) — TIDAK lagi "idempoten diam",
#   karena justru itu yang dulu membuat file `services:` null bertahan permanen.
#
#   Setelah "up", skrip mencetak IP tiap container pada `forcad_default` —
#   itulah IP yang dipakai untuk argumen <svc-ip> checker, BUKAN IP host,
#   BUKAN port yang dipublish ke host. WAJIB konfirmasi manual sebelum gate:
#     docker exec <celery-id> curl -m5 <ip>:<port>/
#
# CATATAN build (dipelajari dari greple): docker CLI di server ini TIDAK
# punya plugin `buildx`. `docker compose build/up --build` mencetak
# peringatan "requires buildx plugin to be installed" tapi TETAP jalan lewat
# classic builder — bukan fatal. Yang FATAL adalah Dockerfile yang memakai
# `RUN --mount=type=cache,...` (butuh BuildKit asli); kalau ketemu itu, hapus
# flag --mount dari RUN tsb pada SALINAN di server (~/adlab/eno10/$SVC, JANGAN
# ubah source asli di laptop) — cache mount cuma optimisasi build ulang,
# bukan kebutuhan fungsional.
#
# CATATAN lain: kalau service pakai toolchain eksotik (mis. Zig) dan versi
# compiler dari package manager alpine/apk berbeda dari yang dipakai penulis
# asli, build bisa gagal karena drift API stdlib. Itu bug SERVICE, bukan
# checker — patch seperlunya di salinan server kalau kecil & mekanis (lihat
# contoh greple: rename variabel shadowing + signature std.fs writeFile baru
# di task-2-report.md), atau laporkan BLOCKED kalau build genuinely rusak.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

SVC="$1"; ACT="${2:-up}"
SRC="$HOME/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/$SVC"
WORK="$HOME/adlab/eno10/$SVC"
cd "$WORK"

if [ "$ACT" = "down" ]; then
  docker compose down -v
  exit 0
fi

# --- tempel semua service ke network forcad_default ---
# BUG LAMA (Task 5): override ditulis HANYA kalau belum ada. Kalau
# `docker compose config --services` sempat kosong di run pertama, file ditulis
# dengan `services:` null; karena file lalu sudah ada, ia tak pernah diperbaiki
# dan semua panggilan compose sesudahnya gagal. FIX: buang override lama dulu
# (agar tak mencemari query maupun bertahan kalau rusak), ambil daftar service,
# lalu regenerasi HANYA bila daftar itu tak kosong. Kosong = compose tak
# resolvable -> gagal keras dgn pesan jelas, JANGAN tulis file rusak.
OVERRIDE="docker-compose.override.yml"
rm -f "$OVERRIDE"
SERVICES="$(docker compose config --services 2>/dev/null || true)"
if [ -z "$(printf '%s' "$SERVICES" | tr -d '[:space:]')" ]; then
  echo "FATAL: 'docker compose config --services' kosong di $WORK —" >&2
  echo "       compose file tak resolvable (cek docker-compose.yml). Override tak ditulis." >&2
  exit 1
fi
{
  echo "services:"
  for s in $SERVICES; do
    echo "  $s:"
    echo "    networks: [default, forcad_default]"
  done
  echo "networks:"
  echo "  default: {}"
  echo "  forcad_default:"
  echo "    external: true"
} > "$OVERRIDE"
echo "ditulis $OVERRIDE:"
cat "$OVERRIDE"

docker compose up -d --build
docker compose ps

echo
echo "IP container pada forcad_default (pakai ini utk gate, BUKAN host IP):"
for cid in $(docker compose ps -q); do
  name=$(docker inspect "$cid" --format '{{.Name}}' | tr -d /)
  ip=$(docker inspect "$cid" --format '{{with index .NetworkSettings.Networks "forcad_default"}}{{.IPAddress}}{{end}}' 2>/dev/null || true)
  echo "  $name -> ${ip:-<tidak di forcad_default>}"
done
