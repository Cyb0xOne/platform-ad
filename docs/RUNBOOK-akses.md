# Runbook Akses Lab A/D

Cara masuk ke lab: submit flag, akses vulnbox, dan port tiap service.

## Endpoint

| Apa | Alamat |
|---|---|
| Scoreboard ForcAD (bawaan) | http://192.168.43.136:8080 |
| Dashboard War Room (custom) | http://192.168.43.136:8090 |
| Flag receiver | http://192.168.43.136:8080/flags/ |
| Vulnbox Athena | 10.13.37.11 |
| Vulnbox Ares | 10.13.37.12 |

## Submit flag

Token tim **adalah** kredensial submit — dikirim sebagai header `X-Team-Token`.
Token tidak lagi tampil di War Room publik. Operator mengambil token dari listener
admin melalui SSH tunnel, lalu membagikannya ke pemilik tim lewat kanal terpisah:

```bash
ssh -L 8091:127.0.0.1:8091 adlab
curl http://127.0.0.1:8091/api/admin/team/<team_id>/token
```

Token yang pernah tampil di War Room sebelum pemisahan listener harus dirotasi
sebelum ronde bernilai dimulai.

```bash
curl -X PUT http://192.168.43.136:8080/flags/ \
     -H "X-Team-Token: <token tim>" \
     -H "Content-Type: application/json" \
     -d '["FLAG1=","FLAG2="]'
```

Maksimal 100 flag per request; kirim sekaligus dalam satu request untuk
menghindari rate limit nginx yang membalas `429`. Balasan per flag, contoh:
`{"msg":"... Flag is invalid or too old."}`. Token salah dijawab
`{"error":"Invalid team token."}`.

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
