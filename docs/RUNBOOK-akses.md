# Runbook Akses Lab A/D

Cara masuk ke lab: submit flag, akses vulnbox, dan port tiap service.

## Endpoint

| Apa | Alamat |
|---|---|
| Scoreboard ForcAD (bawaan) | http://100.87.29.122:8080 |
| Dashboard War Room (custom) | http://100.87.29.122:8090 |
| Flag receiver | http://100.87.29.122:8080/flags/ |
| Vulnbox Athena | 10.13.37.11 |
| Vulnbox Ares | 10.13.37.12 |

`100.87.29.122` = alamat server via Tailscale (jalan dari mana saja). Kalau se-LAN
dengan server, `192.168.43.136` juga jalan.

## Submit flag

Cara lengkap: **[`RUNBOOK-submit-flag.md`](RUNBOOK-submit-flag.md)**. Ringkasnya
`PUT http://100.87.29.122:8080/flags/`, header `X-Team-Token: <token tim>`, body
array JSON flag, maks 100 per request (kirim sekaligus untuk hindari `429`).

Token tim **tidak** tampil di dashboard publik dan berganti tiap game di-reset. Pada
deploy sekarang (dashboard listener tunggal `:8090`), operator mengambil token langsung
dari DB engine lalu membagikan lewat kanal terpisah:

```bash
ssh adlab 'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; \
  docker exec -i adlab-dashboard python3' <<'PY'
import os, psycopg2
c = psycopg2.connect(os.environ['FORCAD_DSN']); cur = c.cursor()
cur.execute("SELECT name, token FROM teams ORDER BY id")
for n, t in cur.fetchall(): print(f"{n}\t{t}")
PY
```

> Dashboard aman dua-listener (publik `:8090` + admin loopback `:8091` untuk token &
> kontrol) sudah disiapkan di `deploy/dashboard-cutover.sh` tapi **belum di-cutover** di
> server. Setelah cutover, token diambil lewat `ssh -L 8091:127.0.0.1:8091 adlab`.

## Akses jaringan VM

Subnet `10.13.37.0/24` internal ke bridge libvirt server, tidak routable dari
luar. Server (`infinix-x1-pro`) bertindak sebagai **Tailscale subnet router**,
jadi VM terjangkau dari mana saja tanpa IP publik.

Sekali per mesin klien, cukup:

```bash
sudo tailscale set --accept-routes
```

Jalur darurat kalau Tailscale mati — hanya berlaku bila se-LAN dengan server:

```bash
sudo ip route add 10.13.37.0/24 via 192.168.43.136
```

## SSH ke vulnbox

Autentikasi **kunci saja**: password di-lock dan `PasswordAuthentication no`.
Dua akun per VM:

| Akun | Untuk | Hak |
|---|---|---|
| `team` | peserta | `NOPASSWD: ALL` + grup `docker` |
| `reky` | admin & automation | sama, dipakai skrip deploy |

**Peserta tidak perlu menyalin kunci manual**: buka modal tim di dashboard
`:8090`, tempel isi `~/.ssh/id_ed25519.pub`, tekan **Tambah key**. Kunci masuk
ke `authorized_keys` akun `team` di vulnbox tim itu.

Isi `~/.ssh/config`:

```
Host adlab
    HostName 100.87.29.122
    User reky

Host cyb0x1-athena
    HostName 10.13.37.11
    User team

Host cyb0x1-ares
    HostName 10.13.37.12
    User team
```

Lalu `ssh cyb0x1-athena` / `ssh cyb0x1-ares`.

Source service ada di **`/opt/adlab-eno/<service>/`** (symlink ke
`/home/reky/adlab-eno`), milik grup `adlab` dengan setgid sehingga `team` dan
`reky` sama-sama bisa mengedit. Direktori tidak dipindah karena container yang
berjalan memakai bind mount ke path tersebut.

> `/opt/adlab` (tanpa `-eno`) adalah sisa provisioning game lama — jangan
> dipakai, dan jangan jadikan target symlink: ia direktori nyata, sehingga
> `ln -s` justru membuat tautan di dalamnya tanpa pesan error.

## Port service

Sama di kedua VM. Sumber kebenaran: `docker ps` di VM — perbarui
`SERVICE_PORTS` di `dashboard/backend/app.py` bila roster berubah.

| Service | Port | Service | Port |
|---|---|---|---|
| example | 10000 | superregister | 6767 |
| greple | 7770-7778 | inbox | 1234, 4321 |
| d3pl0y | 2553 | overeats | 5432 |
| flagdrive | 4859 | leet-date | 6789 |
| signmemaybe | 1984 | funsplash | 1337 |

Tidak semua berbicara HTTP, jadi dashboard sengaja menampilkan `host:port`
apa adanya tanpa menebak protokol.

## Catatan operasional

- Aturan nft yang mengizinkan trafik masuk ke VM **tidak persisten**; jalankan
  ulang `deploy/fase05-gate.sh` setelah reboot host atau restart network libvirt,
  kalau tidak checker akan membaca semua service `DOWN`.
- Shell SSH non-interaktif di server ber-PATH kosong. Skrip lewat SSH wajib
  diawali `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin;`
  — termasuk sebelum memanggil `bash -s`, karena `bash` sendiri tak ditemukan
  tanpa PATH.
