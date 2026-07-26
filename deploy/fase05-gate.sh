#!/usr/bin/env bash
# FASE 0.5 — GATE konektivitas: container checker ForcAD harus bisa membuka
# koneksi BARU ke service di dalam VM tim.
#
# Kenapa ini gate tersendiri: aturan iptables bawaan libvirt hanya mengizinkan
# paket RELATED,ESTABLISHED masuk ke jaringan virtual, lalu me-REJECT sisanya.
# Artinya VM bisa menghubungi keluar, tapi checker TIDAK bisa menghubungi VM —
# dan seluruh service akan terbaca DOWN dengan sebab yang menyesatkan.
#
# Skrip ini: (1) uji dari host, (2) uji dari container celery, (3) kalau gagal
# pasang rule forward, (4) uji ulang. Idempoten.

set -uo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

SUBNET=10.13.37
BRIDGE=virbr-adnet
PROBE_PORT=10000
VMS=("athena|$SUBNET.11" "ares|$SUBNET.12")

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32mLOLOS\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[1;31mGAGAL\033[0m  %s\n' "$*"; }

CELERY=$(docker ps -qf name=forcad-celery | head -1)
[[ -z $CELERY ]] && { echo "container celery ForcAD tidak jalan"; exit 1; }

# --------------------------------------------------- 1. probe di dalam VM ---
say "Menyalakan probe HTTP di tiap VM (nginx dalam docker, port $PROBE_PORT)"
for entry in "${VMS[@]}"; do
  IFS='|' read -r NAME IP <<< "$entry"
  ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 "reky@$IP" \
    "docker rm -f gate-probe >/dev/null 2>&1; docker run -d --name gate-probe -p $PROBE_PORT:80 --restart unless-stopped nginx:alpine >/dev/null && docker --version" \
    && ok "$NAME ($IP) probe naik" || bad "$NAME ($IP) tidak bisa di-SSH / docker belum siap"
done

# ------------------------------------------------------- 2. uji dari host ---
say "Uji dari HOST (harus selalu lolos — host↔VM diizinkan libvirt)"
for entry in "${VMS[@]}"; do
  IFS='|' read -r NAME IP <<< "$entry"
  curl -s -m 5 -o /dev/null "http://$IP:$PROBE_PORT/" && ok "host -> $NAME" || bad "host -> $NAME"
done

# -------------------------------------------- 3. uji dari container celery ---
gate_test() {
  local pass=0
  for entry in "${VMS[@]}"; do
    IFS='|' read -r NAME IP <<< "$entry"
    if docker exec "$CELERY" python -c "
import socket,sys
s=socket.socket(); s.settimeout(5)
sys.exit(0 if s.connect_ex(('$IP',$PROBE_PORT))==0 else 1)
" 2>/dev/null; then
      ok "celery -> $NAME ($IP)"
    else
      bad "celery -> $NAME ($IP)"
      pass=1
    fi
  done
  return $pass
}

say "GATE: uji dari container celery ForcAD"
if gate_test; then
  echo
  echo "Jalur sudah terbuka tanpa perubahan firewall."
  exit 0
fi

# ------------------------------------------------------ 4. pasang rule fw ---
say "Diblokir seperti diduga — membuka jalur ke $BRIDGE"

# Libvirt modern di Arch memakai backend nftables, BUKAN iptables. Chain
# LIBVIRT_FWI tidak ada; yang memblokir adalah chain `guest_input` di
# tabel `ip libvirt_network`:
#
#   oif "virbr-adnet" ip daddr 10.13.37.0/24 ct state established,related accept
#   oif "virbr-adnet" counter ... reject          <-- koneksi BARU mati di sini
#
# Jadi kita sisipkan accept di atasnya. Ini memang membuat vulnbox bisa
# dihubungi dari luar jaringannya — dan itu justru yang diinginkan: di A/D
# vulnbox memang harus bisa diserang.
if sudo nft list table ip libvirt_network &>/dev/null; then
  if sudo nft -a list chain ip libvirt_network guest_input 2>/dev/null \
     | grep -q "oif \"$BRIDGE\" ip daddr $SUBNET.0/24 accept"; then
    echo "rule nftables sudah ada"
  else
    sudo nft insert rule ip libvirt_network guest_input \
      oif "\"$BRIDGE\"" ip daddr "$SUBNET.0/24" accept \
      && echo "rule nftables disisipkan di guest_input"
  fi
elif sudo iptables -L LIBVIRT_FWI -n &>/dev/null; then
  # jalur lama (backend iptables)
  RULE=(-o "$BRIDGE" -d "$SUBNET.0/24" -j ACCEPT)
  sudo iptables -C LIBVIRT_FWI "${RULE[@]}" 2>/dev/null \
    && echo "rule iptables sudah ada" \
    || { sudo iptables -I LIBVIRT_FWI 1 "${RULE[@]}" && echo "rule iptables dipasang"; }
else
  echo "TIDAK KETEMU backend firewall libvirt (nftables maupun iptables)."
  exit 1
fi

say "GATE: uji ulang"
if gate_test; then
  echo
  echo "GATE LOLOS."
  echo
  echo "PENTING: rule ini TIDAK persisten. Libvirt menulis ulang tabel"
  echo "libvirt_network setiap kali network di-restart atau host di-reboot."
  echo "Jalankan ulang skrip ini setelah reboot, atau pasang systemd unit."
  exit 0
fi

echo
echo "Masih gagal. Periksa berurutan:"
echo "  sudo nft list chain ip libvirt_network guest_input"
echo "  sudo nft list chain ip filter FORWARD | head"
echo "  docker network inspect forcad_default -f '{{.Id}}'"
exit 1
