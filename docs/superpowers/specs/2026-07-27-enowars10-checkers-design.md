# Spec: Checker enowars10 (11 service) — checklib native ForcAD

Tanggal: 2026-07-27 · Status: disetujui, siap ke rencana implementasi

## Context

Bank soal A/D punya 41 service dari 8 sumber. Setelah Fase 0–3 platform terpadu
(ForcAD + 3 adapter + dashboard) terbukti berjalan, tersisa gap cakupan. Survei
lengkap menunjukkan **30 dari 41 service coverable** oleh adapter/drop-in yang
sudah ada, tetapi **11 service `enowars10-2026` tidak** — sumbernya adalah repo
tim (bukan rilis panitia) yang hanya berisi *service* + laporan recon (bahasa
Jepang), **tanpa checker resmi sama sekali**.

User memilih menutup gap enowars10 lebih dulu, karena web platform yang akan
di-enhance berikutnya butuh service A/D deployable sebagai isinya. Deliverable
spec ini: **menulis 11 checker dari nol** sehingga ke-11 service enowars10 bisa
di-check UP oleh ForcAD dan ikut ke dalam permainan.

Sumber utama desain checker: `enowars10-2026/shining-arc-team-repo/docs/
2026-07-18_services-overview-report.md` — mendokumentasikan endpoint, port,
auth, dan protokol tiap service secara rinci (sengaja tanpa lokasi flag).

## Keputusan arsitektur: checklib native, bukan enochecker3+adapter

Karena checker ditulis **dari nol** (tak ada checker enochecker3 bawaan untuk
ditiru), formatnya bebas. Dipilih **checklib native ForcAD** — file Python yang
memakai `checklib.BaseChecker`, drop-in ke direktori `checkers/` seperti jalur
blitz/omctf yang sudah terbukti. checklib tidak peduli *cara* bicara ke service,
jadi ke-11 (HTTP, IMAP/SMTP, CLI teks, telnet PDP-11) semua muat dalam satu
format.

Ditolak: enochecker3 + adapter + sidecar. Alasannya sumber daya — tiap *service*
enowars10 sendiri sudah berat (`mediocre` = 11 container, `OverEats`/`leet-date`
= 5–6 container); menambah 11 sidecar checker + mongo di server 15 GB tidak muat.
checklib native jalan langsung di container celery, nol overhead tambahan.

## Layout repo

```
checkers/
  enowars10/
    _lib/
      adlab_eno.py         # harness bersama (lihat §Harness)
    greple/checker.py      # satu direktori per service, checker.py executable
    d3pl0y/checker.py
    flagdrive/checker.py
    signmemaybe/checker.py
    overeats/checker.py
    funsplash/checker.py
    leet-date/checker.py
    superregister/checker.py
    inbox/checker.py
    mediocre/checker.py     # spike riset (lihat §Risiko)
    enomoloch/checker.py    # spike riset
```

Ini direktori BARU `checkers/` — berbeda dari `adapters/` (yang membungkus
checker asli). Di sini kita **penulis** checker-nya, bukan pembungkus.

Deploy: tiap `checker.py` disalin ke celery `/checkers/eno10_<svc>/checker.py`
bersama `_lib/`; didaftarkan di `config.yml` sebagai task dengan
`checker_type: ''`. Dependency baru ditambahkan (BUKAN ditimpa) ke
`checkers/requirements.txt`: `pexpect` (telnet mediocre). `requests` dan
`checklib` sudah ada di image celery; `imaplib`/`smtplib`/`socket` stdlib.

## Kontrak checker & pola flag_id

Kontrak ForcAD (terverifikasi, lihat `docs/plan.md` §Kontrak checker):

```
checker.py check <host>
checker.py put   <host> <flag_id> <flag> <vuln>
checker.py get   <host> <flag_id> <flag> <vuln>
```

Exit code via `checklib.Status`: `OK 101 / CORRUPT 102 / MUMBLE 103 / DOWN 104 /
ERROR 110`. Pola BaseChecker native:

```python
class Checker(BaseChecker):
    def check(self):
        # verifikasi service hidup & fungsional dasar
        self.cquit(Status.OK)
    def put(self, flag_id, flag, vuln):
        creds = ...daftar user acak & simpan flag di resource...
        self.cquit(Status.OK, encode_state(**creds))   # stdout -> flag_id GET
    def get(self, flag_id, flag, vuln):
        st = decode_state(flag_id)
        got = ...login & ambil flag pakai st...
        self.assert_eq(got, flag, 'flag hilang', Status.CORRUPT)
        self.cquit(Status.OK)
```

**Pola flag_id seragam:** putflag membangkitkan kredensial acak, menyimpan flag
di sebuah resource, lalu meng-encode kredensial (username/password/id resource)
sebagai state ke stdout via `cquit(Status.OK, state)`. Karena `checker_type:''`,
string itu disimpan sebagai `private_flag_data` (tidak tampil di scoreboard) dan
dikembalikan sebagai argumen `flag_id` saat GET. getflag men-decode, login, dan
mengambil flag.

Catatan A/D: untuk jalur serang sungguhan penyerang butuh petunjuk flag_id
publik (`checker_type: pfr`) — itu penyempurnaan per-service di kemudian hari,
di luar cakupan spec ini yang fokus ke **kebenaran checker** (UP/CORRUPT/DOWN).

## Harness bersama `_lib/adlab_eno.py`

Menghindari 11× duplikasi. API modul:

- `rand_username()`, `rand_password()`, `rand_text(n)` — pembangkit acak.
- `http(host, port, timeout=10)` — `requests.Session` dengan timeout default,
  retry pada kegagalan koneksi, dan base-url `http://{host}:{port}`.
- `encode_state(**kw) -> str` / `decode_state(s) -> dict` — JSON kompak untuk
  flag_id; `decode_state` melempar status ERROR bila tak terbaca.
- `LineClient(host, port, timeout)` — socket TCP baris: `sendline`,
  `recv_until`, `close`. Untuk superregister (:6767) dan sebagian inbox.
- `expect_session(host, port)` — pembungkus pexpect untuk mediocre (telnet
  DSM-11): `expect`, `sendline`.
- `map_exception(exc) -> Status` — normalisasi: `ConnectionError`/`timeout`/
  `OSError` → DOWN; `AssertionError`/`KeyError`/`ValueError` → MUMBLE; sisanya
  ERROR. (Melengkapi idiom `checklib.assert_*` + `cquit`.)

Tiap `checker.py` jadi tipis — hanya logika spesifik service (endpoint mana,
field mana yang memuat flag).

## Peta flag per service

Recon tak menyebut lokasi flag; kolom "menyimpan/membaca" adalah pilihan desain —
**resource ber-auth apa pun yang round-trip valid** cukup untuk checker yang
benar. Default berikut diturunkan dari endpoint di report; resource final
dikonfirmasi terhadap service yang berjalan saat implementasi.

| # | Service | Port | putflag | getflag | Tier |
|---|---|---|---|---|:--:|
| 1 | greple | 7777 | `POST /pastebin` (flag di body paste) | `GET /p/{hex}` | 1 |
| 2 | d3pl0y | 2553 | `PUT /user/{u}/{name}` (flag = isi objek) | `GET /user/{u}/{name}` (Basic auth) | 1 |
| 3 | flagdrive | 4859 | `POST /api/file/upload` (multipart, visibility=private) | `POST /api/file/download/{id}` (token) | 1 |
| 4 | signmemaybe | 1984 | `POST /api/contracts` (flag di content, header `X-Session-Token`) | `GET /api/contracts/{id}` | 1 |
| 5 | overeats | 5432 | buat order → order note / chat message berisi flag | login → baca note/chat | 1 |
| 6 | funsplash | 1337 | `join` → upload foto/koleksi (flag di deskripsi; body ≤1000 B) | baca foto/koleksi | 1 |
| 7 | leet-date | 6789 | `register` → set bio profil (`PATCH /api/me`) atau kirim pesan | baca profil/pesan | 1 |
| 8 | superregister | 6767 | protokol CLI: `Register` → `AddVehicle` + note (flag di note) | `Login` → `ReadNote` | 2 |
| 9 | inbox | 4321/1234 | SMTP `AUTH PLAIN` → kirim email (flag di body) ke user segar | IMAP login → fetch email | 2 |
| 10 | mediocre | 1980 | telnet DSM-11 → simpan record/global berisi flag | login → baca record | 3 |
| 11 | enomoloch | 8005 | upload pcap berisi flag ke volume `/pcaps` | query Arkime API (Elasticsearch) untuk sesi berisi flag | 3 |

## Gate uji per checker

Disiplin sama dengan 3 adapter Fase 1. Sebelum sebuah checker didaftarkan ke
`config.yml`:

1. Jalankan **service-nya** (`docker compose up` di VM atau host).
2. Manual dari dalam container celery:
   `check <ip>` → 101 · `put <ip> "" <flag> 0` → 101 (tangkap stdout=flag_id) ·
   `get <ip> <flag_id> <flag> 0` → 101.
3. Jalur gagal: `get` dengan flag_id yang tak pernah ditaruh → **102**;
   `check` ke host tanpa service → **104**.
4. Baru daftarkan; verifikasi ronde penuh di engine (`Finished testing … UP`).

## Urutan implementasi

- **Gelombang 1 — Tier 1 (7 HTTP):** greple, d3pl0y, flagdrive, signmemaybe,
  overeats, funsplash, leet-date. Bangun `_lib/adlab_eno.py` lebih dulu (dipakai
  semua), lalu checker dari yang REST-nya paling bersih (greple/d3pl0y/flagdrive)
  ke yang lebih berlapis (overeats/leet-date).
- **Gelombang 2 — Tier 2 (2 TCP):** superregister (klien baris + admin
  challenge-response), inbox (SMTP kirim + IMAP fetch).
- **Gelombang 3 — Tier 3 (2 spike):** mediocre (otomasi terminal DSM-11),
  enomoloch (craft pcap + API Arkime).

## Sumber daya & deployment

VM tim 3 GB masing-masing; **tidak semua 11 service muat bersamaan** (`mediocre`
saja 11 container). Konsekuensi:

- **Pengujian satu service per satu waktu** — spin up, uji checker, tear down.
  `mediocre` mungkin butuh diuji di host/VM tersendiri.
- **Pemilihan service aktif untuk game sungguhan = keputusan runtime**, bukan
  bagian spec ini. Deliverable = 11 checker yang benar, bukan 11 service jalan
  serentak.

## Risiko

- **Tier 3 rapuh.** `mediocre` menuntut otomasi terminal DSM-11 (sistem informasi
  RS bergaya MUMPS 1970-an) — memahami perintah penyimpanan record-nya adalah
  riset tersendiri. `EnoMoloch` menuntut crafting pcap yang memuat flag + query
  API Arkime/Elasticsearch berautentikasi. Keduanya spike: bila setelah usaha
  wajar tak landing, checker ditandai *best-effort* dan **9 lainnya tetap jadi**.
  9 checker solid tidak ditahan demi 2 yang mungkin buntu.
- **Kejutan per-service.** Pengalaman Fase 1 (apt basi, packagist mati, libGL,
  IPv6 bracket, indeks vuln) menunjukkan tiap service menabrak masalah build/
  runtime unik. Anggaran waktu per checker harus memuat debugging semacam itu.
- **Lokasi flag "resmi" bisa beda.** Recon tak menyebutnya; kita memakai resource
  round-trip apa pun. Checker tetap BENAR (UP saat sehat, CORRUPT saat flag
  hilang), hanya mungkin tak menyasar vuln yang diniatkan panitia — tak masalah
  untuk tujuan platform latihan.
- **Bahasa/dependency eksotik service.** Membangun sebagian service (Gleam, Zig,
  Hare, Rust, .NET, SimH) bisa menabrak masalah build seperti shetcode. Itu
  masalah *service*, bukan checker — tapi memblokir gate uji sampai teratasi.

## Di luar cakupan

- Penyempurnaan `checker_type: pfr` (petunjuk flag_id publik untuk penyerang) —
  per-service, kemudian.
- Menulis exploit untuk service enowars10 (checker ≠ exploit).
- Menjalankan semua 11 service serentak; pemilihan roster game.
- Enhance web platform (tujuan user berikutnya, terpisah).

## Verifikasi

1. Tiap checker: gate 3-langkah lolos (101·101·101 + 102 + 104) terhadap
   service yang berjalan.
2. Terdaftar di `config.yml`, ronde penuh di engine menunjukkan `CHECK UP ·
   PUT UP · GET UP` untuk kedua tim.
3. Dashboard menampilkan service baru di grid scoreboard.
4. Tier 3: bila spike buntu, terdokumentasi mengapa; 9 checker Tier 1–2 tetap
   lolos verifikasi #1–3.
