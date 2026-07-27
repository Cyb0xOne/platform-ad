# Handoff — Checker enowars10

**Tanggal:** 2026-07-27
**Branch:** `enowars10-checkers` (18 commit di atas `main`, sudah di-push ke `origin`)
**Status:** 10 dari 12 task selesai. 9 checker service + 1 harness, semuanya lolos gate
terhadap service yang benar-benar berjalan.

Dokumen ini cukup untuk melanjutkan dari komputer lain tanpa konteks percakapan
sebelumnya. Baca ini dulu, lalu `docs/superpowers/reports/enowars10-checkers/00-ledger.md`
untuk detail per-task.

---

## 1. Mulai dari sini

```bash
git clone git@github.com:Cyb0xOne/platform-ad.git
cd platform-ad
git checkout enowars10-checkers
```

Yang wajib dibaca, urut:

| Berkas | Isi |
|---|---|
| `docs/superpowers/specs/2026-07-27-enowars10-checkers-design.md` | Spec desain |
| `docs/superpowers/plans/2026-07-27-enowars10-checkers.md` | Rencana 12 task + Global Constraints |
| `docs/superpowers/reports/enowars10-checkers/00-ledger.md` | **Ledger** — riwayat keputusan & temuan lintas-task |
| `docs/superpowers/reports/enowars10-checkers/task-N-report.md` | Laporan lengkap tiap task (transkrip recon, bukti gate) |
| `deploy/patches/README.md` | Patch build 3 service + cara pakai |

> **Penting:** direktori kerja SDD (`.superpowers/sdd/`) **git-ignored**. Isinya sudah
> disalin ke `docs/superpowers/reports/enowars10-checkers/`. Kalau melanjutkan dengan
> skill `subagent-driven-development`, salin balik dulu:
> ```bash
> mkdir -p .superpowers/sdd/2026-07-27-enowars10-checkers
> cp docs/superpowers/reports/enowars10-checkers/00-ledger.md \
>    .superpowers/sdd/2026-07-27-enowars10-checkers/progress.md
> cp docs/superpowers/reports/enowars10-checkers/task-*.md \
>    .superpowers/sdd/2026-07-27-enowars10-checkers/
> ```
> Baris pertama `progress.md` harus tetap menyebut path plan — itu yang dipakai skill
> untuk mengenali ledger miliknya.

---

## 2. Apa yang sudah jadi

Semua di `checkers/enowars10/`. Tiap checker sudah dibuktikan terhadap instance
service yang berjalan, bukan sekadar ditulis.

| Task | Service | Port | Protokol | Commit | Catatan |
|---|---|---|---|---|---|
| 1 | *(harness)* | — | — | `a71f2ec` | `_lib/adlab_eno.py` + unit test |
| 2 | greple | 7777 | HTTP | `a8ab85d` | pastebin (Zig) |
| 3 | d3pl0y | 2553 | HTTP | `bf26cbe` | object store, Basic auth (Hare) |
| 4 | flagdrive | 4859 | HTTP | `315b437` | file store, multipart (Rust) |
| 5 | signmemaybe | 1984 | HTTP | `66779c6` | contracts (.NET) |
| 6 | overeats | 5432 | HTTP | `2bc1cb0` | order note (Python, 5 container) |
| 7 | funsplash | 1337 | HTTP | `af74796` | foto/koleksi (Gleam) |
| 8 | leet-date | 6789 | HTTP | `bc05406` | profil bio (Go, 6 container) |
| 9 | superregister | 6767 | TCP | `be13dc8` | CLI mentah |
| 10 | inbox | 4321/1234 | SMTP+IMAP | `9021649` | Go kustom |

Definisi "lolos gate" (5 kasus, dijalankan dari dalam container celery):
`check`→101, `put`→101, `get`→101, `get` flag_id-ngawur→102, `check` host mati→104.

---

## 3. Sisa pekerjaan

### Task 11 — `mediocre` (:1980, telnet DSM-11) — SPIKE
### Task 12 — `enomoloch` (:8005, pcap + Arkime API) — SPIKE

Keduanya ditandai **best-effort di spec**. BLOCKED adalah hasil yang sah: kalau
service-nya tidak bisa dibangun, tulis `checkers/enowars10/<svc>/BLOCKED.md` berisi
transkrip + hambatan, commit, lanjut. Sembilan checker lain tetap utuh.

> ⚠️ **Cacat di brief Task 11 — jangan diikuti mentah.** Brief menyuruh memakai
> `adlab_eno.expect_session` (pexpect). **Fungsi itu tidak ada.** Harness hanya punya:
> `rand_username`, `rand_password`, `rand_text`, `encode_state`, `decode_state`,
> `http`, `LineClient`, `status_for`.
> Pakai `LineClient` (soket mentah, tangani negosiasi telnet IAC sendiri). Menambah
> `pexpect` berarti mengubah `requirements.txt` + blok CUSTOMIZE `Dockerfile.fast` +
> rebuild image celery — menyentuh kesepuluh checker demi satu spike. Jangan, kecuali
> terbukti tidak ada jalan lain.

### Setelah Task 11–12

1. **Review menyeluruh satu branch** (model paling mampu, bukan default sesi).
2. **Perbaiki `deploy/enowars10-deploy.sh`** — lihat §5.
3. **Susun `config.enowars10.yml`** — lihat §6. Ini yang mengubah 10 checker jadi
   permainan yang benar-benar jalan.
4. Tutup branch (`superpowers:finishing-a-development-branch`).

---

## 4. Infrastruktur

```
Server ForcAD : ssh reky@192.168.43.136
ForcAD        : ~/adlab/forcad
Container      : forcad-celery   (checker di-mount ke /checkers)
Sumber service : ~/adlab/eno10/<service>          (di server)
Sumber bersih  : ~/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/<service>/
VM tim         : 10.13.37.11 (Cyb0x1 Athena) / 10.13.37.12 (Cyb0x1 Ares)
```

Hal yang menggigit kalau lupa:

- **PATH kosong di shell SSH non-interaktif.** Awali dengan
  `export PATH=/usr/bin:/bin:/usr/sbin:/sbin;` atau pakai `bash -lc`.
  Untuk `rsync` ke server, wajib `--rsync-path=/usr/bin/rsync`.
- **BuildKit TIDAK ada di host server.** `RUN --mount=type=cache` gagal.
  **Docker di VM tim punya BuildKit yang berfungsi** — membangun di VM menghindari
  patch itu sama sekali.
- **RAM server ketat (~6.6 Gi bebas).** Pola wajib: `up` → gate → `docker compose down -v`.
  Jangan tinggalkan service menyala.
- **Checker berjalan sebagai `nobody`** di celery — jangan menulis ke path milik root.
- **Iterasi cepat:** `docker cp` checker ke container celery lalu jalankan ulang. Tidak
  perlu rebuild selama tidak ada dependency baru.

### Memilih tempat menjalankan service saat gate

Periksa `docker-compose.yml` dulu:

- Kalau container **listen di port checker secara internal** → attach ke jaringan
  `forcad_default`, gate ke container IP. (Task 2–5, 7, 9, 10)
- Kalau port itu **hanya host-publish** ke port internal berbeda
  (mis. `ports: ["6789:8080"]`) → pola di atas mustahil; jalankan di VM tim, gate ke
  IP VM. (Task 6, 8)

Gate selalu: `docker exec forcad-celery <path checker> <aksi> <ip> ...`

---

## 5. Utang teknis

### ✅ Ditutup saat handoff — patch build
Dulu hanya hidup di salinan server; `rsync` ulang dari sumber bersih akan mengulang
kegagalan. Sudah diekstrak ke `deploy/patches/`:

- `greple.patch` — Dockerfile (buang cache mount) **+ `src/utils.zig`** (API
  `std.fs.cwd().writeFile` Zig berubah). Bagian `utils.zig` sebelumnya tidak
  tercatat di ledger.
- `flagdrive.patch` — Dockerfile (5 blok cache mount) + `frontend/index.html`
  (bug upstream: href aset tailwind salah path).
- `funsplash.patch` — `bravo` dari git dependency jadi path lokal. **Butuh langkah
  manual:** vendor ulang `vendor/bravo` (perintah di `deploy/patches/README.md`).

### ❗ Belum ditutup — bug `deploy/enowars10-deploy.sh`
**Sudah benar-benar menggigit sekali** (Task 5), bukan teoretis. Script menulis
`docker-compose.override.yml` **hanya kalau berkas itu belum ada**. Kalau
`docker compose config --services` sempat mengembalikan kosong di run pertama, ia
meninggalkan override rusak dengan kunci `services:` null — dan karena berkasnya sudah
ada, tidak pernah memperbaiki diri. Semua panggilan compose sesudahnya gagal.

Workaround selama ini: hapus override, tulis tangan.
Perbaikan sebenarnya: regenerasi kalau berkas tidak valid, atau jangan tulis sama
sekali kalau daftar service kosong.

### Kebersihan kecil
Ada skrip verifikasi manual tertinggal di layer writable container celery
(`/tmp/manual_verify.py`), tidak bisa dihapus karena permission. Tidak berbahaya;
hilang saat rebuild image celery berikutnya.

---

## 6. Registrasi config — batas yang mengikat

**`config.enowars10.yml` sengaja belum disentuh.** Registrasi ditunda sampai semua
checker jadi, karena dibatasi RAM server dan timing ronde.

### Batas reaper — ini yang paling mudah bikin salah

Lima service menghapus data tersimpan setelah waktu tertentu:

| Service | Reaper | Mekanisme |
|---|---|---|
| d3pl0y | ~12 menit | TTL objek |
| flagdrive | ~12 menit | TTL user/file |
| overeats | 12 menit | `cleanup_old_data()` di `init.sql` |
| inbox | ~12 menit | cron tiap 3 mnt hapus dir user > 12 mnt; **tidak** disegarkan aktivitas |
| leet-date | 15 menit | container cleanup hapus baris `users` |
| superregister | — | prune berbasis **kapasitas** (10.000 terbaru), bukan waktu |

Artinya: **`round_time × flag_lifetime` harus ≤ ~720 detik.**

`forcad/config.fase1.yml` sekarang memakai `round_time: 180` dengan `flag_lifetime: 5`
= **900 detik — melanggar batas ini.** Kalau dipakai apa adanya, `get` terhadap flag
lama akan gagal dan skor jatuh padahal service sehat.

Pilihan: turunkan `round_time` ke 120 (600 s, aman) atau `flag_lifetime` ke 3.

### Usulan `checker_timeout` per service

Dari pengalaman gate: overeats 30 (7 round-trip HTTP berurutan, terbanyak),
signmemaybe 25, inbox 25, superregister 20, leet-date 15. Sisanya belum diusulkan
eksplisit — ambil dari `checker_timeout` di brief masing-masing.

Ingat kontrak ForcAD: `round_time` ≥ 4× `checker_timeout` terbesar.

### RAM
Menjalankan sembilan service sekaligus **belum pernah dicoba**. Tiap gate selama ini
hanya menyalakan satu service lalu mematikannya. overeats (5 container) dan leet-date
(6 container) yang paling berat. Kalau semua tidak muat, sebarkan ke dua VM tim, atau
daftarkan sebagian dulu.

---

## 7. Pengetahuan yang mahal didapat

Ini yang akan memakan waktu berjam-jam kalau ditemukan ulang dari nol.

### Tentang checklib

- **`assert_*` gagal itu MELEMPAR `CheckFinished`**, bukan `sys.exit` langsung.
  Konsekuensinya ada dua, keduanya penting:
  1. `try/finally: close()` **selalu** jalan → socket tidak pernah bocor.
  2. Membungkus assertion di dalam `except Exception` akan **menelan** klasifikasi
     status dan mengubahnya jadi ERROR (110). Template di brief Task 10 punya cacat
     ini; jangan disalin. `CheckFinished` adalah subclass langsung `Exception`.
- **Peringatan pyright "not a known attribute of None" setelah `assert_` itu false
  positive** — pyright tidak tahu `assert_` tidak pernah kembali saat gagal (tidak
  dianotasi `NoReturn`). Berlaku di semua checker.
- Konstruksi `Checker` **di luar** `try` di blok `__main__` itu load-bearing: kalau di
  dalam dan konstruktornya melempar, klausa `except c.get_check_finished_exception()`
  mereferensikan `c` yang unbound → `NameError` lolos dari jaring.

### Tentang harness (`_lib/adlab_eno.py`)

- Di-deploy **sekali** ke `/checkers/_lib` sebagai **sibling** tiap direktori checker.
  Tiap `checker.py` menjangkaunya lewat `sys.path` ke `parent.parent/_lib`.
- **Jangan diubah tanpa pertimbangan lintas-task** — sepuluh checker bergantung padanya.
- `status_for` punya cabang `isinstance(exc, OSError) → DOWN`. **`smtplib.SMTPException`
  diam-diam subclass `OSError`** — kalau lolos tak tertangkap, server SMTP yang hidup
  tapi salah akan salah dilaporkan DOWN.
- `flag_id` yang bukan JSON → `decode_state` `ValueError` → MUMBLE, bukan CORRUPT.
  Diterima sadar: di produksi `flag_id` selalu berasal dari `put` sebelumnya.

### Tentang jaringan & protokol

- **Cookie `Secure` di atas HTTP polos.** wisp (Gleam) menandai cookie sesi `Secure`
  untuk host apa pun kecuali literal `localhost`/`127.0.0.1`. `requests.Session` di atas
  `http://` **tidak pernah** mengirimnya balik — dan checker selalu menembak IP tim,
  tidak pernah localhost. Solusi "buku teks" (`DefaultCookiePolicy` dengan
  `secure_protocols`) **tidak berpengaruh**, karena `Session.prepare_request` membungkus
  ulang cookie ke jar baru dan membuang policy kustom. Yang berhasil: salin nilai cookie
  ke header `Cookie` manual (lihat `_sync_cookie_header` di `funsplash/checker.py`).
- **Redirect membuat assert status berbohong.** `requests` mengikuti redirect secara
  default; kalau tujuannya halaman catch-all yang selalu 200, `assert_eq(status, 200)`
  selalu lolos — assertion mati. Pakai `allow_redirects=False` di request yang di-assert.
- **`imaplib` bisa balas `('OK', [None])`** kalau baris untagged FETCH tak pernah datang.
  Jaga dengan `if fdat[0] else b""`, jangan `or b""` (yang melempar `TypeError` →
  ERROR alih-alih CORRUPT).

### Tentang ForcAD

- **Format flag: `[A-Z0-9]{31}=`.** Tidak mungkin mengandung koma, spasi, atau huruf
  kecil — aman disisipkan ke format berdelimiter apa pun.
- `checker_type: ''` → `flag_id` privat, tidak tampil di scoreboard.
- Dependency checker masuk lewat blok CUSTOMIZE `docker_config/celery/Dockerfile.fast`
  lalu `control.py build --fast`. `start` saja **tidak** me-rebuild.
- `checkers/requirements.txt` di server **ditambah, jangan ditimpa** — dipakai bersama
  semua checker.

### Pola kerja yang terbukti

- **Brief selalu salah.** Sepuluh dari sepuluh service berbeda dari tebakan brief —
  route, nama field, casing, atau content-type. Yang terparah `superregister`, di mana
  nyaris seluruh protokolnya meleset. **Baca sumber service, lalu konfirmasi dengan
  curl/soket nyata sebelum menulis checker.**
- **Jangan bergantung pada vuln yang disengaja.** `superregister` punya IDOR di
  `ReadNote <a> <b>` (otorisasi lewat `<a>`, baca note `<b>`). Checker mengirim id
  sendiri untuk kedua argumen. Checker yang bergantung pada vuln akan rusak persis saat
  sebuah tim menambalnya — menghukum tim yang bertahan dengan benar.
- **`get()` harus membuktikan round-trip jujur.** Assert pada isi yang benar-benar
  disimpan dan dikembalikan service untuk resource spesifik itu — bukan sesuatu yang
  dikirim request yang sama, dan bukan lewat jalur yang tetap lolos seandainya flag
  ditimpa lawan. Lebih baik assert field JSON yang sudah di-parse daripada substring
  body mentah.

---

## 8. Celah yang diketahui

Jujur dicatat, bukan disembunyikan:

- **Gate 5-kasus tidak pernah menguji "flag masih ada tapi DIUBAH."** Yang diuji hanya
  flag *hilang* (id tak ada → 404 → CORRUPT). Sifat "isi diubah → CORRUPT" diverifikasi
  lewat pembacaan kode oleh reviewer di Task 3–10, bukan secara empiris. Padahal itu
  justru kasus paling menentukan di permainan nyata. Kalau mau benar-benar yakin,
  tambahkan kasus gate ke-6: PUT → timpa isi lewat API → GET harus 102.
- **Blok `__main__` identik byte-per-byte di sepuluh checker.** Kandidat refactor jadi
  helper di `_lib` — tapi **hanya setelah** semua checker jadi, supaya tidak menyentuh
  ulang file yang sudah lolos gate.
- **Menjalankan sembilan service serentak belum pernah diuji** (lihat §6).
- Temuan Minor yang sengaja ditunda tercatat per-task di ledger dengan penanda
  `minor (deferred)` — jadikan masukan untuk review menyeluruh nanti.

---

## 9. Verifikasi cepat kalau ragu

```bash
# semua checker ada?
ls checkers/enowars10/

# server hidup?
ssh reky@192.168.43.136 'export PATH=/usr/bin:/bin; docker ps --format "{{.Names}}"'

# jalankan ulang satu checker (contoh: greple) — service harus dinyalakan dulu
ssh reky@192.168.43.136 'export PATH=/usr/bin:/bin; \
  docker exec forcad-celery /checkers/eno10_greple/checker.py check <ip>; echo "exit=$?"'
```

Exit code yang diharapkan: 101 OK · 102 CORRUPT · 103 MUMBLE · 104 DOWN · 110 ERROR.
