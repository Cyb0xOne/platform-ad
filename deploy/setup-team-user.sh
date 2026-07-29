#!/usr/bin/env bash
# Siapkan akun peserta di vulnbox: user `team`, hostname tim, akses source service.
# Dijalankan DI DALAM VM.  pakai: setup-team-user.sh <hostname-baru>
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

NEWHOST="${1:?hostname baru wajib diisi}"
SRC=/home/reky/adlab-eno

# 1. user peserta: sudo penuh (tim harus bisa patch OS/service) + docker tanpa sudo
if ! id team >/dev/null 2>&1; then
  sudo useradd -m -s /bin/bash team
  echo "  user team dibuat"
else
  echo "  user team sudah ada"
fi
sudo usermod -aG docker team
echo 'team ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/90-team >/dev/null
sudo chmod 440 /etc/sudoers.d/90-team
sudo visudo -c -f /etc/sudoers.d/90-team >/dev/null && echo "  sudoers valid"

# 2. source service dipakai bersama reky (automation) & team (peserta).
#    Tidak dipindah: container yang berjalan memakai bind mount ke path ini,
#    memindahkannya akan memutus mount. setgid supaya berkas baru ikut grup.
sudo groupadd -f adlab
sudo usermod -aG adlab reky
sudo usermod -aG adlab team
if [ -d "$SRC" ]; then
  sudo chgrp -R adlab "$SRC"
  sudo chmod -R g+rwX "$SRC"
  sudo find "$SRC" -type d -exec chmod g+s {} +
  sudo chmod o+x /home/reky
  # /opt/adlab sudah dipakai provisioning game lama; pakai nama sendiri supaya
  # symlink tidak malah dibuat DI DALAM direktori itu.
  sudo ln -sfn "$SRC" /opt/adlab-eno
  echo "  source dibagikan lewat grup adlab, symlink /opt/adlab-eno"
fi

# 3. kunci: dashboard boleh menitipkan pubkey peserta ke akun team
sudo -u team mkdir -p /home/team/.ssh
sudo -u team chmod 700 /home/team/.ssh
sudo cp /home/reky/.ssh/authorized_keys /home/team/.ssh/authorized_keys
sudo chown team:team /home/team/.ssh/authorized_keys
sudo chmod 600 /home/team/.ssh/authorized_keys
echo "  authorized_keys team: $(sudo cat /home/team/.ssh/authorized_keys | wc -l) kunci"

# 4. hostname (beserta /etc/hosts agar sudo tidak lambat/mengeluh)
sudo hostnamectl set-hostname "$NEWHOST"
sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$NEWHOST/" /etc/hosts
grep -q "127.0.1.1" /etc/hosts || echo -e "127.0.1.1\t$NEWHOST" | sudo tee -a /etc/hosts >/dev/null
echo "  hostname -> $(hostname)"
