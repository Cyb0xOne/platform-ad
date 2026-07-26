#!/usr/bin/env bash
# FASE 0.5 — provisioning vulnbox VM + gate konektivitas.
#
# Dijalankan DI SERVER (192.168.43.136). Idempoten: aman diulang.
#
# Membuat:
#   - network libvirt "adnet"  (NAT, 10.13.37.0/24, bridge virbr-adnet)
#   - VM "ad-athena" -> 10.13.37.11   (tim Cyb0x1 Athena)
#   - VM "ad-ares"   -> 10.13.37.12   (tim Cyb0x1 Ares)
#     masing-masing Debian 13 cloud, 3 GB RAM, 2 vCPU, disk 20 GB, docker terpasang.
#
# TIDAK menyentuh network week4-* maupun VM vm-a / vm-b / vm-obs yang sudah ada.
#
# Subnet 10.13.37.0/24 dipilih karena bebas: server sudah memakai 172.17-172.31
# (bridge docker), 10.0.0.0/24, 10.10.10.0/24, 192.168.122.0/24 (week4-nat),
# 192.168.0.0/20, 192.168.43.0/24, 192.168.49.0/24.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

NET=adnet
BRIDGE=virbr-adnet
SUBNET=10.13.37
IMG_DIR=/var/lib/libvirt/images
WORK=$HOME/adlab/vms
# Rencana awal Debian 13, tapi cloud.debian.org tidak dapat dihubungi dari
# jaringan server (permintaan tunggal balik http=000). Dialihkan ke Ubuntu
# 22.04 cloud; untuk vulnbox keduanya setara. Ganti dua baris ini kalau
# suatu saat mau kembali ke Debian.
#
# CATATAN mengukur kecepatan mirror: hotspot server membatasi koneksi
# serentak. Mengukur kecepatan SAAT ada unduhan lain berjalan menghasilkan
# angka palsu (0-15 KB/s) dan bikin mirror sehat terlihat mati. Ukur satu
# per satu. Kecepatan asli cloud-images.ubuntu.com di sini ~1,8 MB/s.
BASE_URL=https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
BASE=$WORK/jammy-base.img
PUBKEY=$(cat "$HOME/.ssh/id_rsa.pub")

# nama | mac | ip terakhir | hostname
VMS=(
  "ad-athena|52:54:00:ad:13:11|11|athena"
  "ad-ares|52:54:00:ad:13:12|12|ares"
)

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

mkdir -p "$WORK"

# ---------------------------------------------------------------- network ---
say "Network $NET"
if virsh -c qemu:///system net-info "$NET" &>/dev/null; then
  echo "sudah ada, dilewati"
else
  cat > "$WORK/$NET.xml" <<XML
<network>
  <name>$NET</name>
  <forward mode='nat'/>
  <bridge name='$BRIDGE' stp='on' delay='0'/>
  <ip address='$SUBNET.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='$SUBNET.100' end='$SUBNET.200'/>
      <host mac='52:54:00:ad:13:11' name='athena' ip='$SUBNET.11'/>
      <host mac='52:54:00:ad:13:12' name='ares'   ip='$SUBNET.12'/>
    </dhcp>
  </ip>
</network>
XML
  virsh -c qemu:///system net-define "$WORK/$NET.xml"
  virsh -c qemu:///system net-autostart "$NET"
  virsh -c qemu:///system net-start "$NET"
  echo "dibuat"
fi

# ------------------------------------------------------------- base image ---
say "Base image Ubuntu 22.04 cloud"
if [[ -f $BASE ]]; then
  echo "sudah ada ($(du -h "$BASE" | cut -f1)), dilewati"
else
  # -c wajib: koneksi hotspot sering putus, dan mengulang 350 MB dari nol itu mahal.
  # Jangan menjalankan uji kecepatan paralel ke host yang sama — hotspot membatasi
  # koneksi serentak, dan koneksi kedua akan gagal sehingga terlihat seperti
  # mirror mati padahal unduhan utama sehat.
  wget -c -q --show-progress -O "$BASE.part" "$BASE_URL"
  mv "$BASE.part" "$BASE"
fi

# WAJIB. Kejadian nyata: image lama di ~/vm-images/ ternyata hasil unduhan yang
# tidak selesai — qcow2-nya mereferensikan cluster di luar batas file. VM tetap
# terbuat dan "running", tapi mati dengan IO error di log qemu dan tidak pernah
# mengambil IP. Gejalanya menyesatkan (mirip salah konfigurasi jaringan),
# jadi lebih baik gagal di sini, keras dan jelas.
if ! qemu-img check "$BASE" >/dev/null 2>&1; then
  echo "FATAL: base image $BASE korup / tidak lengkap."
  echo "Hapus lalu jalankan ulang skrip ini supaya diunduh bersih:"
  echo "  rm -f $BASE"
  qemu-img check "$BASE" 2>&1 | tail -3
  exit 1
fi
echo "integritas base image OK"

# --------------------------------------------------------------------- VM ---
for entry in "${VMS[@]}"; do
  IFS='|' read -r NAME MAC LAST HOST <<< "$entry"
  say "VM $NAME -> $SUBNET.$LAST"

  if virsh -c qemu:///system dominfo "$NAME" &>/dev/null; then
    echo "sudah terdefinisi, dilewati"
    continue
  fi

  # disk: salinan penuh dari base, dibesarkan ke 20 GB
  sudo cp "$BASE" "$IMG_DIR/$NAME.qcow2"
  sudo qemu-img resize "$IMG_DIR/$NAME.qcow2" 20G

  # seed cloud-init
  SEED=$WORK/$NAME-seed
  mkdir -p "$SEED"
  cat > "$SEED/meta-data" <<META
instance-id: $NAME
local-hostname: $HOST
META
  cat > "$SEED/user-data" <<USER
#cloud-config
hostname: $HOST
manage_etc_hosts: true

users:
  # JANGAN masukkan grup "docker" di sini — grup itu belum ada sebelum docker
  # terpasang, dan cloud-init akan gagal membuat user (artinya SSH terkunci).
  # Penambahan ke grup docker dilakukan di runcmd setelah instalasi.
  - name: reky
    groups: [sudo]
    shell: /bin/bash
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    lock_passwd: false
    ssh_authorized_keys:
      - $PUBKEY

package_update: true
packages: [ca-certificates, curl]

runcmd:
  # docker resmi (repo Debian kadang ketinggalan compose v2)
  - [ sh, -c, "curl -fsSL https://get.docker.com | sh" ]
  - [ usermod, -aG, docker, reky ]
  - [ systemctl, enable, --now, docker ]
  - [ mkdir, -p, /opt/adlab ]
  - [ chown, "reky:reky", /opt/adlab ]
  # penanda: dipakai skrip gate untuk tahu provisioning selesai
  - [ sh, -c, "docker --version > /var/lib/cloud/adlab-ready 2>&1" ]
USER
  genisoimage -quiet -output "$WORK/$NAME-seed.iso" -volid cidata -joliet -rock \
    "$SEED/user-data" "$SEED/meta-data"
  sudo cp "$WORK/$NAME-seed.iso" "$IMG_DIR/$NAME-seed.iso"

  virt-install \
    --connect qemu:///system \
    --name "$NAME" \
    --memory 3072 --vcpus 2 \
    --disk "path=$IMG_DIR/$NAME.qcow2,format=qcow2,bus=virtio" \
    --disk "path=$IMG_DIR/$NAME-seed.iso,device=cdrom" \
    --network "network=$NET,mac=$MAC,model=virtio" \
    --osinfo detect=on,require=off \
    --graphics none --noautoconsole --import
  virsh -c qemu:///system autostart "$NAME"
  echo "dibuat & dinyalakan"
done

say "Status"
virsh -c qemu:///system list --all | grep -E "ad-athena|ad-ares|Name|---" || true
echo
echo "Lanjut: tunggu cloud-init selesai (~2-4 menit), lalu jalankan deploy/fase05-gate.sh"
