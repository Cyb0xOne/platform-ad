# Task 10 Report: Checker `inbox` (:4321 SMTP / :1234 IMAP) — custom Go dual-protocol

## Status: DONE

Checker ditulis, di-deploy ke `forcad-celery-1:/checkers/eno10_inbox/checker.py`, dan digate
penuh terhadap instance live `inbox` yang dijalankan di server (`192.168.43.136`), di-attach ke
`forcad_default` dan digate lewat IP kontainernya (`192.168.0.17`, port 1234 IMAP + 4321 SMTP).
Kelima kasus gate wajib LOLOS tepat sesuai kontrak: **101 / 101 / 101 / 102 / 104**. Tidak ada
patch build server yang diperlukan sama sekali. Ini checker **kedua** dari 11 yang protokolnya
line-protocol (setelah superregister/Task 9), dan **pertama** yang memakai stdlib `smtplib`/
`imaplib` sungguhan — dikonfirmasi bekerja penuh untuk setiap operasi standar yang dibutuhkan,
dengan `A.LineClient` dipakai sempit hanya untuk satu langkah non-standar (REGISTER).

BASE commit: `be13dc8` (superregister, Task 9). Commit task ini: `083bc54`.

## Ringkasan alur

1. Baca brief (`task-10-brief.md`) dan catatan defect eksplisit soal `try/except Exception`
   membungkus `assert_*` (menelan `CheckFinished`).
2. Baca `checkers/enowars10/_lib/adlab_eno.py` (harness bersama, tak dimodifikasi) dan
   `checkers/enowars10/superregister/checker.py` sebagai model shape/konvensi komentar.
3. Baca seluruh source Go (`internal/session/commands.go`, `session.go`, `extras.go`,
   `internal/smtp/server.go`, `internal/imap/parser.go`, `internal/imap/response.go`,
   `internal/db/db.go`, `cmd/inboxd/main.go`) — ini yang membongkar mekanisme REGISTER,
   parser tokenizer, dan bug literal APPEND (lihat §Temuan) SEBELUM menyentuh service live,
   supaya recon live lebih terarah.
4. rsync source laptop → server (`~/adlab/eno10/inbox/`, exclude `maildir/` dan `.git/`).
5. `docker compose build` di server (BUKAN VM) — **sukses bersih tanpa modifikasi apa pun**
   (`FROM golang:1.26-trixie`, tanpa `RUN --mount=type=cache` sama sekali).
6. `docker compose up -d` — log konfirmasi **kedua port listen langsung di dalam kontainer**
   (`INBOX (IMAP) listening on [::]:1234`, `INBOX (SMTP) listening on [::]:4321`), dan
   `docker-compose.yml` map `"1234:1234"` + `"4321:4321"` (host:container identik) — sesuai
   pola "attach ke `forcad_default`", BUKAN VM tim.
7. **Recon manual multi-sesi** (socket Python mentah DAN stdlib `smtplib`/`imaplib` langsung,
   dari laptop ke `192.168.43.136` selagi port masih host-published) — lihat §Transkrip.
   Recon ini membuktikan (bukan cuma membaca source) bahwa stdlib bekerja penuh, DAN menemukan
   dua jebakan nyata (§Temuan #3 bug APPEND, §Temuan #4 jebakan klasifikasi OSError) yang tidak
   akan terlihat dari sekadar membaca source.
8. Tulis `checkers/enowars10/inbox/checker.py`, uji cepat lokal (venv `.venv-eno`, Python
   3.11.15 — SENGAJA dipakai drpd Python 3.14 sistem, supaya perilaku `imaplib`/`smtplib`
   yang diuji cocok dgn interpreter celery 3.11) langsung ke `192.168.43.136` untuk iterasi
   tanpa perlu docker-cp berulang ke celery.
9. Deploy ke celery: `~/adlab/forcad/checkers/eno10_inbox/checker.py` di host (otomatis
   ter-mount ke `/checkers/eno10_inbox/` di `forcad-celery-1`), `chmod 755`.
10. `docker network connect forcad_default inbox_service-inbox-1` → IP `192.168.0.17`.
    Dikonfirmasi **kedua port** reachable dari `forcad-celery-1` SEBELUM menulis checker akhir
    (`socket.create_connection` ke `.17:1234` dan `.17:4321`, keduanya membalas banner benar).
11. Gate 5 kasus wajib dari dalam `forcad-celery-1` (`docker exec`, user default `nobody`,
    dicek `id` → `uid=65534(nobody) gid=65534(nogroup)`). Semua 5 LOLOS pada percobaan checker
    final (lihat §Gate) — tanpa iterasi ulang setelah pindah dari lokal ke celery.
12. Teardown: `docker compose down -v` di server (container + network project `inbox_service`
    dihapus bersih; RAM kembali ke ~6.9Gi available, sama seperti baseline). File scratch
    `/tmp` di server dibersihkan.
13. Commit **hanya** `checkers/enowars10/inbox/checker.py` (`083bc54`). Config
    (`config.enowars10.yml`) **TIDAK disentuh**, **TIDAK ada engine round** — sesuai resolusi
    eksplisit ambiguitas brief Step 4 (ditunda, gate menggantikannya sbg bukti).

## Bagaimana akun dibuat — REGISTER via IMAP, BUKAN auto-create saat LOGIN

Brief menduga dua kemungkinan ("auto-created on LOGIN, or there may be a registration step").
**Dikonfirmasi keduanya: bukan auto-create, memang ada langkah registrasi eksplisit**, via
command IMAP kustom `REGISTER <user> <pass>`.

Dari source (`internal/session/commands.go`):
- `cmdLogin`/`cmdAuthenticate` memanggil `s.db.Authenticate(username, password)`, yang membaca
  file `users/<u>/password` — kalau tak ada, `Authenticate` return `(User{}, false)` tanpa efek
  samping apa pun (TIDAK membuat user baru). Hasilnya: `"LOGIN failed: invalid credentials"`.
- `cmdRegister` adalah SATU-SATUNYA jalur pembuatan akun: valid hanya di state
  `StateNotAuthenticated`, memanggil `s.db.CreateUser(username, password)` lalu
  `s.db.EnsureInbox(username)`. Diiklankan lewat `CAPABILITY` (`... REGISTER ...`).
- SMTP **tidak punya jalur registrasi sama sekali** — `cmdAuth` (SMTP AUTH PLAIN) juga cuma
  `s.db.Authenticate`; `cmdRcpt` mensyaratkan `s.db.UserExists(local)`. Jadi urutan yang benar
  wajib: REGISTER dulu lewat IMAP, baru SMTP AUTH+RCPT ke akun yang sama akan diterima.

Dikonfirmasi LIVE (bukan cuma dari source):
```
>>> a1 CAPABILITY
<<< * CAPABILITY IMAP4rev1 AUTH=PLAIN NAMESPACE ID UIDPLUS METADATA AUDITLOG REGISTER ARCHIVE ELEV_AGENT
    a1 OK CAPABILITY completed

>>> a2 REGISTER reconuser1 reconpass1
<<< a2 OK REGISTER completed

>>> a3 REGISTER reconuser1 reconpass1        (duplikat)
<<< a3 NO REGISTER failed: user already exists

>>> a4 LOGIN reconuser1 reconpass1
<<< a4 OK LOGIN completed

(koneksi baru)
>>> b1 LOGIN reconuser1 wrongpass
<<< b1 NO LOGIN failed: invalid credentials
>>> b2 LOGIN nosuchuser whatever
<<< b2 NO LOGIN failed: invalid credentials
```
**Penting**: pesan LOGIN gagal utk "password salah pada user yang ADA" dan "user yang TAK ADA"
**identik byte-for-byte**. Ini yang menentukan pilihan kasus bogus/CORRUPT gate (lihat §Gate) —
kredensial salah/tak-ada TIDAK BISA dipakai utk menguji CORRUPT krn keduanya jatuh ke MUMBLE.

`put()` checker ini melakukan REGISTER lewat `A.LineClient` (satu request/response, lihat
§Jalur stdlib vs LineClient), baru mengirim flag lewat SMTP dgn kredensial yg sama.

## Jalur stdlib vs `A.LineClient` — HAMPIR SELURUHNYA stdlib, LineClient sempit untuk satu command

**stdlib `smtplib`/`imaplib` bekerja PENUH untuk setiap operasi standar** yang checker ini
butuhkan — dikonfirmasi live, Python 3.11.15 (venv `.venv-eno`, versi yg sama dgn interpreter
celery 3.11.6):

- SMTP: `EHLO`, `AUTH PLAIN` (`smtplib.SMTP.login`), `MAIL FROM`/`RCPT TO`/`DATA`
  (`smtplib.SMTP.send_message`) — semua diterima tanpa modifikasi.
- IMAP: `LOGIN`, `SELECT`, `SEARCH` (termasuk `SEARCH SUBJECT "<value>"` yg di-quote), `FETCH
  (RFC822)`, `NOOP`, `CAPABILITY` (implisit lewat constructor `imaplib.IMAP4`) — semua diterima
  tanpa modifikasi.

**Satu-satunya operasi yang TAK PUNYA representasi stdlib**: `REGISTER`. Ini BUKAN kasus
"server custom menolak handshake standar" (kontras dgn framing brief yg menyarankan fallback
LineClient "kalau server menolak") — servernya menerima SEMUA framing IMAP standar dgn benar.
Masalahnya murni di sisi CLIENT: `imaplib.IMAP4._command` menggerbangi setiap nama command lewat
dict internal `Commands` yg cuma berisi verb IMAP4rev1 asli; `"REGISTER"` bukan anggotanya:
```
KeyError: 'REGISTER'
  File ".../imaplib.py", line 1089, in _command
    if self.state not in Commands[name]:
```
**Keputusan**: `A.LineClient` dipakai SEMPIT hanya untuk satu request/response REGISTER ini
(connect → buang greeting → `sendline("a1 REGISTER {u} {p}")` → `recv_until(b"\r\n")` → assert
→ close), lalu koneksi `imaplib`/`smtplib` TERPISAH dan bersih dipakai untuk sisanya. Alternatif
yang SENGAJA DIHINDARI: monkey-patch `imaplib.Commands['REGISTER'] = ('NONAUTH',)` (jalan, sudah
dicoba saat recon dan berhasil) — tapi mengubah state GLOBAL modul stdlib demi satu command
custom terasa lebih rapuh drpd satu koneksi `LineClient` sekali pakai yg sudah terbukti aman di
Task 9. Ini beda karakter dgn superregister (Task 9): di sana SELURUH protokol harus manual
(CLI custom tanpa akar protokol standar); di sini HAMPIR SELURUH protokol adalah IMAP/SMTP
standar asli, dan LineClient cuma menambal satu ekstensi non-standar.

## Temuan penting (diverifikasi live, bukan diasumsikan)

### 1. Bug server: IMAP `APPEND` lewat `imaplib` RUSAK terhadap server ini

Dicoba `im.append("INBOX", None, None, body)` (jalur natural utk put() via IMAP murni, sblm
memutuskan pakai SMTP) — **hasilnya selalu desync**: `APPEND` sendiri sukses (`OK [APPENDUID
...] APPEND completed`), tapi command BERIKUTNYA pada koneksi yg SAMA (`SEARCH`) langsung
`imaplib.IMAP4.abort: socket error: EOF` — koneksi ditutup paksa oleh server TANPA log apa pun
(container log hanya berisi baris startup, `Debug` flag mati).

Sebab (dikonfirmasi dari `internal/imap/parser.go`, method `consumeLiteral`): server membaca
PERSIS N byte literal via `io.ReadFull(r.r, buf)` sesuai deklarasi `{N}`, tapi TAK PERNAH
menguras CRLF penutup yang standar IMAP4 (RFC 3501) wajibkan client kirim SETELAH byte literal
(bagian dari framing baris command). `imaplib.IMAP4._command` MEMANG mengirim CRLF itu
(`self.send(literal); self.send(CRLF)`). CRLF nyasar itu tertinggal di `bufio.Reader` sisi
server; `ReadCommand()` berikutnya membacanya sbg baris KOSONG → `parseLine("")` → tag kosong →
`fmt.Errorf("empty tag")` → `Session.Run()`'s loop `return`-diam-diam (bukan `io.EOF`, tapi
`Debug` mati jadi tak ada log) → koneksi tertutup tanpa respons ke command berikutnya.

**Konsekuensi desain**: checker ini TIDAK PERNAH memakai IMAP `APPEND`. Pengiriman flag di
`put()` dilakukan lewat SMTP `DATA` saja — yang kebetulan juga pas dgn tuntutan brief "buktikan
KEDUA protokol/port hidup", bukan cuma IMAP.

### 2. Jebakan klasifikasi: `smtplib.SMTPException` adalah turunan `OSError`

Diverifikasi via `type(e).__mro__` pada percobaan login SMTP salah dan RCPT ke user tak-ada:
```
smtplib.SMTPAuthenticationError.__mro__ =
    (SMTPAuthenticationError, SMTPResponseException, SMTPException, OSError, Exception, BaseException, object)
smtplib.SMTPRecipientsRefused.__mro__ =
    (SMTPRecipientsRefused, SMTPException, OSError, Exception, BaseException, object)
```
Konfirmasi dari source stdlib: `class SMTPException(OSError): ...` (`smtplib.py` baris 72).
**Kalau checker ini membiarkan exception ini lolos ke handler generik `__main__`/`status_for`
(gaya sketsa brief: `except Exception as e: self.cquit(A.status_for(e), ...)`), cabang
`isinstance(exc, OSError)` di `status_for` akan mengklasifikasikan PENOLAKAN PROTOKOL (password
SMTP salah, RCPT ke user tak ada) sbg DOWN (104)** — padahal service-nya HIDUP dan menjawab
dgn semantik yg benar (seharusnya MUMBLE, 103). Ini kesalahan yg SANGAT mudah lolos kalau hanya
mengandalkan intuisi "smtplib exception ya pasti generic Exception".

`imaplib.IMAP4.error` (dipakai al. `login()` gagal) sebaliknya BUKAN turunan `OSError`
(`(IMAP4.error, Exception, BaseException, object)`) — tapi tetap tak dikenali cabang mana pun
di `status_for`, jatuh ke default `Status.ERROR` (110), juga salah (harusnya MUMBLE sesuai
tuntutan eksplisit task: "A failed login in get() is MUMBLE, not CORRUPT" — dan implisit juga
bukan ERROR).

**Mitigasi**: checker ini menangkap KEDUA exception ini secara EKSPLISIT & SEMPIT (nama kelas
spesifik: `except imaplib.IMAP4.error` / `except smtplib.SMTPException`) di setiap tempat
`smtplib`/`imaplib` dipakai, menerjemahkan sendiri ke `Status.MUMBLE` — TIDAK PERNAH dibiarkan
jatuh ke `status_for` generik. Diverifikasi empiris (bukan cuma dibaca dari kode) bahwa hasilnya
memang `103` — lihat §Verifikasi tambahan.

### 3. Cacat brief (dihindari) — tidak direproduksi sama sekali

Sesuai catatan tugas: SETIAP `except` di checker final menyebut kelas exception SPESIFIK
(`imaplib.IMAP4.error` / `smtplib.SMTPException`), bukan `except Exception`. Kedua kelas ini
BUKAN leluhur `checklib.CheckFinished` (`class CheckFinished(Exception)`, exception yg dilempar
`assert_*`/`cquit`) — jadi `CheckFinished` tak pernah tertangkap tak sengaja, baik `assert_*`
diletakkan di dalam maupun di luar blok `try`. Diverifikasi: semua kasus gate (termasuk MUMBLE
dan CORRUPT) menghasilkan status code yg BENAR, bukan ke-reklasifikasi jadi ERROR (lihat §Gate
dan §Verifikasi tambahan).

## Transkrip protokol yang dikonfirmasi (byte-for-byte, dari recon live)

**Greeting** (dipakai `check()`):
```
IMAP: b'* OK INBOX ready\r\n'
SMTP: b'220 inbox.local SMTP ready\r\n'
```

**EHLO** (dipakai `check()` sbg bukti dispatch loop SMTP hidup, bukan cuma banner statis):
```
250-inbox.local hello <client>
250-PIPELINING
250-8BITMIME
250-AUTH PLAIN
250-SIZE 1048576
250 HELP
```

**Round-trip penuh** (REGISTER via LineClient → SMTP AUTH PLAIN+MAIL+RCPT+DATA via stdlib →
IMAP LOGIN+SELECT+SEARCH+FETCH via stdlib), dari uji `try_full311.py`:
```
>>> REGISTER fllyrvfrbm ppqbquhvtgtfma      (via IMAP, LineClient)
<<< OK REGISTER completed

>>> EHLO loq-irx10.localdomain
<<< 250 ... AUTH PLAIN ...
>>> AUTH PLAIN AGZsbHlydmZyYm0AcHBxYnF1aHZ0Z3RmbWE=
<<< 235 2.7.0 authentication successful
>>> MAIL FROM:<fllyrvfrbm@inbox.local> size=208
<<< 250 2.1.0 OK
>>> RCPT TO:<fllyrvfrbm@inbox.local>
<<< 250 2.1.5 OK
>>> DATA
<<< 354 end with <CRLF>.<CRLF>
>>> From: fllyrvfrbm@inbox.local\r\nTo: ...\r\nSubject: SUBJ-5A7FLH2147\r\n...\r\n\r\nFLAGTESTVALUE_9NK39JD1UC=\r\n.\r\n
<<< 250 2.0.0 OK message queued

>>> LOGIN fllyrvfrbm ppqbquhvtgtfma          (via IMAP, imaplib)
<<< OK LOGIN completed
>>> SELECT INBOX
<<< ... a5 OK [READ-WRITE] SELECT completed
>>> SEARCH ALL
<<< SEARCH 1 / OK
>>> FETCH 1 (RFC822)
<<< * 1 FETCH (RFC822 {N}\r\n<pesan lengkap termasuk Subject & flag>)
=== TARGETED FLAG FOUND: True ===
```

**SEARCH SUBJECT tepat-sasaran** (dipakai `get()` — bukan scan seluruh mailbox):
```
>>> SEARCH SUBJECT "SUBJ<value-cocok>"
<<< SEARCH 1 / OK
>>> SEARCH SUBJECT "SUBJ<value-tak-cocok>"
<<< SEARCH  (kosong) / OK
```

## Verifikasi tambahan (di luar 5 kasus gate wajib, dijalankan lokal thd host live)

Dijalankan via `.venv-eno` (Python 3.11.15) langsung ke `192.168.43.136` sblm masuk gate resmi
di celery, utk memvalidasi klasifikasi §Temuan #2 & #3 empiris:
```
get() dgn password SALAH (akun nyata)         -> 103 MUMBLE
    error(b'LOGIN failed: invalid credentials')
get() dgn akun TAK PERNAH ada sama sekali      -> 103 MUMBLE
    error(b'LOGIN failed: invalid credentials')
```
Keduanya `103`, BUKAN `102` (CORRUPT, salah) ataupun `110` (ERROR, salah kalau exception lolos
ke handler generik) — mengonfirmasi baik kepatuhan pada aturan "login gagal di get() = MUMBLE"
maupun penanganan jebakan §Temuan #2 (imaplib.IMAP4.error tertangkap & diterjemahkan benar,
tidak jatuh ke default ERROR).

## Gate — lima kasus wajib

Dijalankan dari `forcad-celery-1` (`docker exec`, user `nobody` — dicek `id` →
`uid=65534(nobody) gid=65534(nogroup)`), target `192.168.0.17` (IP `forcad_default` milik
kontainer `inbox_service-inbox-1`, port 1234 IMAP / 4321 SMTP keduanya dicek reachable dari
`forcad-celery-1` SEBELUM iterasi checker dimulai):

```
1. check (live)                                                       → 101
2. put   (live)                                                       → 101
   stdout (flag_id) = {"u":"DeftMaple6657","p":"vAVaigLc3zBEiuZa","s":"SGladFalcon8747"}
3. get   (flag_id di atas, flag sama "GATEFLAGINBOXTASK10AAAAAAAAAAA=")  → 101
4. get   (state well-formed, kredensial SAMA/NYATA dari put() #2 di atas,
          subject diganti "SNoSuchMessageEverSent0000" — pesan itu
          tak pernah dikirim)                                          → 102
   pesan: "pesan dgn subject kita tak ditemukan di mailbox"
   detail: [__main__.Checker.get:234] assertion failed
5. check (host tak ada rute, 192.168.0.250 di forcad_default)          → 104
   detail: checker error / OSError(113, 'No route to host')
```

**Pilihan kasus bogus (#4)**: kredensial NYATA & HIDUP (login akan genuinely SUKSES), hanya
subjectnya yang diganti ke nilai yang tak pernah dikirim ke mailbox itu. Ini SENGAJA, bukan
kredensial salah/akun-tak-ada — karena (§Bagaimana akun dibuat di atas) server ini membalas
pesan LOGIN-gagal yang **identik** utk "password salah" maupun "user tak ada", jadi kasus
kredensial-salah akan menguji jalur MUMBLE (dikonfirmasi empiris = 103, lihat §Verifikasi
tambahan), BUKAN CORRUPT. Kasus bogus resmi di atas adalah genuine "flag tak ada di mailbox"
(akun ada & valid, login sukses, tapi pesan yg dicari benar-benar tak pernah ada) — tepat sesuai
arahan task.

Sebelum gate resmi ini, seluruh 5 kasus (dan dua kasus tambahan login-gagal di atas) sudah diuji
lebih dulu **lokal** (venv `.venv-eno`, Python 3.11.15, langsung ke `192.168.43.136` sblm
di-attach ke `forcad_default`) utk iterasi cepat tanpa bolak-balik `docker cp`/`scp` ke celery.
Draf checker final LANGSUNG lolos gate resmi tanpa iterasi ulang setelah pindah ke celery.

Setelah gate: `docker compose down -v` di server (container + network project `inbox_service`
dihapus bersih, dicek `docker ps` kosong utk `inbox`). RAM kembali ke ~6.9Gi available (sama
seperti baseline sblm service dinaikkan; sblm gate sempat turun ke ~6.7Gi available saat idle
dgn service lain juga jalan).

## Build — tanpa patch

`Dockerfile`: `FROM golang:1.26-trixie`, install `cron`, buat user `service` (uid 1000),
`go build -o /service/inboxd ./cmd/inboxd`, `ENTRYPOINT ["/entrypoint.sh"]` (jalankan sbg user
`service` via `su`, plus start `cron` utk `cleanup.sh`). **Tidak ada `RUN --mount=type=cache`
sama sekali** — keterbatasan "BuildKit tak tersedia di server utama" tidak relevan utk service
ini (sama seperti leet-date Task 8 dan superregister Task 9). `docker compose build` dijalankan
apa adanya di server (`192.168.43.136`), sukses bersih (22 langkah Dockerfile, "Successfully
built" + "Successfully tagged"). Warning build yg muncul (`invoke-rc.d: policy-rc.d denied
execution of start`, `sysctl: permission denied on key ...`) adalah noise standar instalasi
paket `cron` lewat `apt-get` di dalam container tanpa systemd/sysctl aktif — BUKAN error, tidak
mempengaruhi hasil build. **Tidak ada diff patch build untuk dicatat.**

## Data expiry — cron 3-menit, TTL 12 menit per-direktori-user (bukan per-baris)

Dikonfirmasi dari source (bukan `strings` biner — service ini Go source lengkap tersedia):
```
cron.d/inbox-cleanup:  */3 * * * * service /cleanup.sh /maildir >/dev/null 2>&1
cleanup.sh:            MAX_AGE_MIN=12
                        find "$MAILDIR/users" -mindepth 1 -maxdepth 1 -type d \
                            -mmin "+$MAX_AGE_MIN" -exec rm -rf {} +
```
Setiap 3 menit, SELURUH direktori user (`maildir/users/<username>/` — berisi file `password`,
seluruh mailbox/pesan, `subscriptions`, `meta`, `auditlog`) yang mtime-nya lebih tua dari 12
menit **dihapus total** (`rm -rf`). Ini konsisten dgn pola "5 dari 9 servis lain hapus data
stlh 12-15 menit" yg disebut brief.

**Detail yg PERLU dicatat (dianalisis dari `internal/db/db.go`, bukan diuji live siklus
penuh)**: `find -mmin` memeriksa mtime DIREKTORI USER ITU SENDIRI (bukan mtime file di
dalamnya, bukan mtime subdirektori mailbox). Menelusuri kode:
- `CreateUser` (saat REGISTER) menulis file `password` LANGSUNG di dalam direktori user →
  membuat/mem-bump mtime direktori user.
- `EnsureInbox` (dipanggil REGISTER **dan** setiap LOGIN/AUTHENTICATE) membuat subdirektori
  mailbox (`mkdir` LANGSUNG di dalam direktori user, kalau blm ada) lalu `Subscribe(...,
  "INBOX")`. `Subscribe` menulis file `subscriptions` LANGSUNG di dalam direktori user HANYA
  kalau mailbox itu BELUM ada di daftar — begitu sekali tersubscribe (saat REGISTER), panggilan
  `EnsureInbox` berikutnya (mis. saat LOGIN di `get()`) akan menemukan "INBOX" SUDAH ada di
  `subscriptions` dan `Subscribe` jadi NO-OP DIAM-DIAM (tak menulis apa pun).
- Pesan mail (`AppendMessage`, dipicu SMTP `DATA` atau IMAP `APPEND`) menulis file `.eml`/`.meta`
  di dalam SUBDIREKTORI mailbox, BUKAN langsung di dalam direktori user — jadi tak mem-bump
  mtime direktori user.
- `writeAuditlog` (dipanggil tiap sesi authenticated DITUTUP) menulis file `auditlog` LANGSUNG
  di dalam direktori user — tapi HANYA mem-bump mtime direktori pada penulisan file PERTAMA kali
  (`os.WriteFile` dgn nama yg sama pada panggilan berikutnya menimpa ISI file, tidak membuat
  entri direktori baru, jadi TIDAK mem-bump mtime direktori parent lagi).

**Kesimpulan**: jam 12 menit itu PRAKTIS mulai dari waktu REGISTER selesai (semua bump mtime
signifikan terjadi di t≈0), dan **TIDAK direfresh** oleh `get()`/login belakangan dgn pola
akses normal (SELECT/SEARCH/FETCH tak pernah menyentuh direktori user langsung). Konsekuensi:
flag efektif harus diambil dlm ~12-15 menit sejak `put()`, TTL akun yg keras (bukan
"refresh-on-access" spt beberapa servis lain).

**TIDAK diverifikasi secara live** (mis. menunggu 12-15 menit nyata utk melihat direktori benar2
terhapus) — analisis di atas dibaca LANGSUNG dari shell script (`cleanup.sh` + `cron.d/inbox-
cleanup`) yang benar-benar dieksekusi cron di container, dan dari jejak kode Go yg menentukan
kapan mtime direktori user berubah — bukan tebakan dari `strings` biner yg tak-di-strip spt
beberapa servis sebelumnya, jadi keyakinan tinggi meski siklus penuhnya tak diamati langsung
(menunggu 15 menit nyata di tengah kendala RAM server terasa tak sepadan drpd membaca source
yg deterministik).

## `checker_timeout: 25` (nilai brief) — tampak memadai, tidak diubah

`put()`: 1 koneksi `LineClient` (greeting + REGISTER, 2 round-trip) + 1 koneksi `smtplib` (EHLO,
AUTH PLAIN, MAIL, RCPT, DATA — konstruksi + ~5 round-trip). `get()`: 1 koneksi `imaplib`
(konstruksi+CAPABILITY implisit, LOGIN, SELECT, SEARCH, FETCH — ~5 round-trip). Semua operasi
di gate live selesai instan (sub-detik agregat per action, tak ada jeda terlihat). Dgn timeout
per-operasi 10 detik (`TIMEOUT = 10` di checker, dipakai baik utk `LineClient` maupun
konstruktor `imaplib.IMAP4`/`smtplib.SMTP`), skenario terburuk satu langkah hang akan
menghabiskan brdrp 10 detik sblm exception keluar bersih (DOWN via `status_for`, krn
`ConnectionError`/`TimeoutError` propagate tak tertangkap oleh except sempit manapun) — jauh di
bawah budget 25 detik. **Tidak diusulkan perubahan.**

## Yang TIDAK diverifikasi / di luar cakupan

- **Siklus penuh reaper 12-15 menit** — lihat §Data expiry, dianalisis dari source (bukan
  `strings`) dgn keyakinan tinggi, tapi tak diamati langsung penghapusan direktori terjadi.
- **Fitur `ELEV_AGENT`** (challenge-response DHE/Ed25519-ish via `gov_verify`/`gov_public.pem`,
  utk menaikkan `GovernmentAgent` flag yg membuka capability `AUDITLOG` lintas-user) — dibaca
  sekilas di source, sama sekali di luar kontrak PUT/GET flag (REGISTER→SMTP DATA→IMAP FETCH),
  tidak disentuh checker.
- Fitur lain yg jauh lebih besar dari cakupan brief, tak disentuh checker: `AUDITLOG` (baca log
  command lintas-user, hanya utk government agent), `ARCHIVE`, `SETMETADATA`/`GETMETADATA`
  (signature footer SMTP), `CREATE`/`DELETE`/`RENAME` mailbox, `COPY`, `STORE`/flags, `EXPUNGE`.
- Perilaku checker di bawah beban paralel (banyak `put`/`get` bersamaan ke servis yg sama) —
  gate hanya menguji sekuensial, konsisten dgn sibling checker lain.
- Konfirmasi bahwa `smtplib`/`imaplib` versi Python 3.11.6 (celery, BUKAN 3.11.15 lokal) punya
  perilaku identik — keduanya sama-sama minor version 3.11, dan modul `smtplib`/`imaplib` tidak
  berubah perilaku antar patch release 3.11.x sejauh yg saya tahu, tapi tidak diverifikasi
  dgn membandingkan source file byte-for-byte antara kedua instalasi.
- Config (`config.enowars10.yml`) dan status `UP` via engine round — sengaja tidak dikerjakan,
  sesuai resolusi ambiguitas brief Step 4.

## Concerns

1. **Tidak ada concern build/infra.** Build bersih tanpa patch, topologi `forcad_default`
   berfungsi langsung tanpa perlu VM tim (kedua port dikonfirmasi listen langsung di dalam
   kontainer, bukan cuma host-publish).
2. **Bug APPEND (§Temuan #1) tidak dilaporkan ke mana pun selain di sini** — kalau ada checker
   lain di masa depan (atau modifikasi checker ini) yg mencoba memakai IMAP `APPEND`, akan
   mengalami kegagalan silent yg sama. Dicatat panjang di komentar checker.py supaya tak
   terulang tanpa perlu recon ulang.
3. **Klasifikasi `smtplib.SMTPException`-sbg-`OSError` (§Temuan #2) adalah jebakan yg mudah
   lolos** kalau checker lain di masa depan menambahkan pemakaian `smtplib` tanpa sadar
   perilaku ini — didokumentasikan panjang di checker.py, tapi `adlab_eno.status_for` sendiri
   TIDAK diubah (sesuai batasan "jangan modifikasi _lib") jadi risiko ini tetap ada utk siapa
   pun yg menulis checker `smtplib` baru tanpa membaca catatan ini.
4. **Koleksi collision username/subject** (`A.rand_username()`, ruang ~504.000 kombinasi) —
   risiko rendah tapi bukan nol dlm jangka panjang siklus checker sungguhan, sama dgn risiko yg
   sudah diterima sibling checker lain (mis. superregister Task 9) yg memakai generator yg sama.
5. Konsisten dgn seluruh sibling checker: `flag_id` yang BUKAN JSON sama sekali (bukan "JSON
   valid tapi field hilang") akan jatuh ke `status_for(ValueError) = MUMBLE` (103), bukan
   CORRUPT — perilaku harness `decode_state`, bukan cacat checker ini. Kasus gate bogus resmi
   (JSON valid, field lengkap, hanya nilai `s` yg tak match) sudah sesuai arahan task.

## File yang relevan

- `checkers/enowars10/inbox/checker.py` (repo, 265 baris) — **satu-satunya file yang di-commit**
  untuk task ini, commit `083bc54`.
- `~/adlab/eno10/inbox/` di server (`192.168.43.136`) — rsync source, **tanpa modifikasi** (tak
  ada patch build yg perlu dipertahankan).
- `forcad-celery-1:/checkers/eno10_inbox/checker.py` (host source:
  `~/adlab/forcad/checkers/eno10_inbox/checker.py`) — dibiarkan terpasang (mode 755, dicek
  `nobody` bisa baca+eksekusi), sama seperti preseden sibling lain.
- Service `inbox` **diturunkan** (`docker compose down -v`) setelah gate — tidak dibiarkan
  jalan, sesuai batasan RAM server.

## Fix round 1 (review finding, Important)

**Finding**: `checker.py:238` (`get()`), `body = fdat[0][1] or b""` bisa melempar `TypeError`
tak tertangkap saat `imaplib._untagged_response` mengembalikan `(typ="OK", dat=[None])` —
bentuk yg muncul ketika `doFetch` (server) membalas tagged OK tanpa baris untagged `* n FETCH
(...)` apa pun (karena `FetchMessages` men-list ulang direktori mailbox scr independen dari
`CountMessages` yg dipakai `ParseSequenceSet`, dan menemukan nol file `.eml` yg cocok, tanpa
error). `TypeError` ini bukan `imaplib.IMAP4.error` jadi lolos dari except sempit di `:243`,
jatuh ke `except Exception` generik `__main__` (:264-265), dan `status_for` tak punya cabang
utk `TypeError` polos → `Status.ERROR` (110) — padahal ini semestinya masuk ruang CORRUPT/MUMBLE
sesuai kontrak (baris SEARCH tepat di atasnya, `:233`, SUDAH dijaga pola stdlib yg sama tapi
baris FETCH dua baris di bawahnya tidak).

**Fix** (satu baris, `checkers/enowars10/inbox/checker.py:238`, commit `9021649`):
```diff
-            body = fdat[0][1] or b""
+            body = fdat[0][1] if fdat[0] else b""
```
Tidak ada perubahan lain — komentar dokumentasi, `rand_username()`, dan seluruh bagian lain
checker TIDAK disentuh, sesuai instruksi scope-ketat review.

### Reproduksi — dikonfirmasi NYATA, bukan spekulasi

Dijalankan thd instance live (`192.168.43.136`, service `inbox` dinaikkan ulang dari image yg
sudah ter-cache, `docker compose up -d`, di-attach ulang ke `forcad_default`, IP `192.168.0.17`
sama spt sebelumnya — tidak perlu rebuild). Skrip debug murni di `/tmp` (scratchpad sesi),
TIDAK ADA yg ditulis ke repo.

**Langkah 1 — buktikan bentuk `('OK', [None])` itu sendiri** (raw `imaplib`, akun
`AbleQuartz2118`): `put()` normal (checker YG SUDAH DIPERBAIKI, tidak relevan dgn bug ini) →
kirim 1 pesan → `LOGIN`+`SELECT`+`SEARCH SUBJECT` (dgn subject asli) → dapat seq `1` → **hapus
`maildir/users/AbleQuartz2118/INBOX/1.eml` lewat shell, direktori & `1.meta`/`uidnext`/
`uidvalidity` DIBIARKAN** → `FETCH` seq `1` yg sama:
```
FETCH result: 'OK' [None]
typ == 'OK': True
fdat == [None]: True
```
Persis bentuk yg diklaim reviewer, dikonfirmasi via `imaplib` sungguhan (bukan dibaca dari
source saja).

**Langkah 2 — reproduksi END-TO-END lewat proses checker.py asli** (bukan cuma snippet
`imaplib` manual): tantangannya, `get()` melakukan SEARCH-lalu-FETCH dlm SATU invokasi — kalau
file dihapus SEBELUM `get()` dijalankan, SEARCH milik `get()` sendiri sudah kosong duluan dan
berhenti di assert CORRUPT baris `:234` (dicoba sekali, terjadi persis begini — dicatat sbg
percobaan pertama yg TIDAK merepresentasikan bug ini dgn tepat). Supaya SEARCH internal
checker sendiri sempat melihat pesan itu SEBELUM file dihapus (window balapan yg sesungguhnya),
dibuat DUA salinan scratch checker (`/tmp/.../unfixed_test/inbox/checker.py` dari isi commit
`083bc54` sblm fix, dan `/tmp/.../fixed_test/inbox/checker.py` dari isi sesudah fix) dgn SATU
baris debug tambahan (`time.sleep(5)`, diberi komentar eksplisit "DEBUG-ONLY... not in shipped
checker") disisipkan PERSIS di antara assert SEARCH (`:234`) dan pemanggilan FETCH (`:236`) —
hook ini murni utk memberi jendela waktu deterministik agar penghapusan file via shell terpisah
bisa dilakukan tepat di tengah satu eksekusi `get()`, dan HANYA ada di dua salinan scratch itu,
tidak pernah di repo.

Utk tiap varian: `put()` akun baru → jalankan `get()` (salinan scratch) di background → tunggu
2 detik (SEARCH sudah lewat, FETCH blm dipanggil, masih di tengah sleep 5 detik) → hapus
`.eml` akun itu lewat shell terpisah → `wait` proses background → periksa exit code.

**Varian TAK DIPERBAIKI** (akun `KeenComet4380`):
```
UNFIXED TIMED-TEST EXIT CODE: 110
TypeError("'NoneType' object is not subscriptable")
checker error
```
✅ Mengonfirmasi finding: 110/ERROR, persis lewat `TypeError` yg diklaim.

**Varian SUDAH DIPERBAIKI** (akun `KeenMaple1849`, race identik):
```
FIXED TIMED-TEST EXIT CODE: 102
[__main__.Checker.get:245] contains assertion failed: b'REPROFLAGBUGWINDOW222222222222=' not in b''
flag tak ada di pesan tersimpan
```
✅ Mengonfirmasi fix: 102/CORRUPT, lewat `assert_in` yg SUDAH ADA (`:242`, sekarang bergeser ke
baris `:245` krn 3 baris debug tambahan) — TANPA cabang baru, persis sesuai usulan reviewer.

**Kesimpulan reproduksi**: window ini REACHABLE dan dikonfirmasi via proses `checker.py` asli
(bukan simulasi/snippet terisolasi), baik utk versi lama (110, bug nyata) maupun versi baru
(102, fix bekerja). Satu-satunya penyimpangan dari resep reviewer: window balapan yg sesungguhnya
berlangsung sub-milidetik antara dua panggilan DB internal server (`CountMessages` lalu
`FetchMessages` di dalam SATU `doFetch`); direproduksi di sini dgn memperlebar window itu scr
artifisial (`time.sleep(5)` di sisi CLIENT, di antara SEARCH dan FETCH milik checker) supaya
penghapusan file via shell bisa "menang" thd waktu nyata — bukan menangkap race asli servernya
(yg pemicunya kemungkinan reaper cron × overlap dgn FETCH sungguhan, keduanya di luar kendali
timing checker), tapi hasil AKHIR yg diserahkan ke `imaplib` (`('OK', [None])`) dan perilaku
checker thd bentuk itu 100% identik dgn skenario race asli — jadi kesimpulan 110→102 berlaku
sah utk kasus ini.

## Gate ulang stlh fix — lima kasus wajib (tak ada regresi)

Dijalankan ulang persis spt gate awal, dari `forcad-celery-1` (`nobody`), thd instance live baru
(image di-cache, tak perlu rebuild), IP `192.168.0.17` (forcad_default):
```
1. check (live)                                                       → 101
2. put   (live)                                                       → 101
   stdout (flag_id) = {"u":"AbleQuartz2267","p":"rZhSD7MKqo05YSqg","s":"SEagerOtter7551"}
3. get   (flag_id di atas, flag sama "GATEFLAGROUND1FIXEDAAAAAAAAAAA=")  → 101
4. get   (state well-formed, kredensial SAMA/NYATA dari put() di atas,
          subject diganti "SNoSuchMessageEverSentR1")                   → 102
5. check (host tak ada rute, 192.168.0.250 di forcad_default)          → 104
```
Identik dgn kontrak gate awal (`101/101/101/102/104`) — **tidak ada regresi**. Setelah gate:
`docker compose down -v` lagi, RAM kembali ke baseline ~6.8Gi available, scratch file server
(`/tmp/inbox-r1-*.txt`) dibersihkan.

## File tambahan yang relevan utk fix round 1

- `checkers/enowars10/inbox/checker.py` — satu baris berubah (`:238`), commit `9021649`.
- `forcad-celery-1:/checkers/eno10_inbox/checker.py` (host:
  `~/adlab/forcad/checkers/eno10_inbox/checker.py`) — di-redeploy dgn isi yg sudah diperbaiki.
- Skrip reproduksi scratch (`/tmp/claude-*/scratchpad/{unfixed_test,fixed_test}/inbox/
  checker.py`, `find_uid.py`, `confirm_bug.py`) — sesi-lokal, TIDAK di-commit, TIDAK ada di
  working tree repo.
