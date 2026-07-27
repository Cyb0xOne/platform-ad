# Task 9 Report: Checker `superregister` (:6767) — protokol CLI TCP

## Status: DONE

Checker ditulis, di-deploy ke `forcad-celery-1:/checkers/eno10_superregister/checker.py`, dan
digate penuh terhadap instance live `superregister` yang dijalankan langsung di server
(`192.168.43.136`), di-attach ke `forcad_default` dan digate lewat IP kontainernya
(`192.168.0.17:6767`). Kelima kasus gate wajib LOLOS tepat sesuai kontrak: **101/101/101/102/104**.
Tidak ada patch build server yang diperlukan sama sekali. Ini checker **pertama** dari 9 yang
protokolnya CLI/TCP baris-per-baris (bukan HTTP) — `A.LineClient` dipakai sungguhan pertama kali,
dan brief-nya secara sengaja tidak lengkap (`# ... jawab prompt ... sesuai interaksi nyata ...`).
Draf final ditulis SETELAH tiga sesi recon manual (socket Python mentah) terhadap instance live,
bukan dari tebakan `strings` semata — dan recon itu membongkar beberapa asumsi brief yang salah
(lihat §Koreksi).

BASE commit: `bc05406` (leet-date). Commit task ini: `be13dc8`.

## Ringkasan alur

1. Baca brief (`task-9-brief.md`) — skeleton eksplisit tidak lengkap di bagian `AddVehicle`.
2. Baca `checkers/enowars10/_lib/adlab_eno.py` (harness bersama) — `LineClient` (`sendline`,
   `recv_until`, `recv`, `close`), `encode_state`/`decode_state`, `status_for`. Belum pernah
   dipakai checker lain; jadi kesempatan pertama membuktikan (atau membantahnya) di jalur nyata.
3. `strings` biner (`bin/SuperRegister`, ELF x86-64 statis, tak di-strip) — dipakai sbg
   **hipotesis awal**, BUKAN kebenaran akhir (persis instruksi task). Menemukan skema DB via
   literal SQL (`CREATE TABLE ... vehicles (... maintenance_note TEXT ...)`, TANPA tabel `notes`
   terpisah) dan daftar command menu (`Add`, `Edit`, `Remove`, `List`, `Search`, `ReadNote`,
   `Diagnostic`, `ReadLog`, `FirmwareDump`, `History`, `Settings`, `Exit`).
4. rsync source laptop → server (`~/adlab/eno10/superregister/`). `rsync` lokal butuh
   `--rsync-path="export PATH=...; rsync"` eksplisit (gotcha PATH-kosong shell non-interaktif,
   sudah didokumentasikan preseden Task 6/7/8) — tanpa itu rsync gagal "command not found:
   rsync" di sisi remote.
5. `docker compose build` di server (BUKAN VM) — **sukses bersih tanpa modifikasi apa pun**.
   Dockerfile (`python:3-alpine` + `apk add g++ sqlite-dev openssl-dev`) tidak punya
   `RUN --mount=type=cache` sama sekali, jadi keterbatasan "BuildKit tak ada di server utama"
   tidak relevan untuk service ini.
6. `docker compose up -d` di server — `docker-compose.yml` map `"6767:6767"` (host:container),
   dan biner mencetak "CTF Vehicle Server listening on port 6767..." — **container benar-benar
   LISTEN di 6767 secara internal** (bukan cuma host-publish ke port lain, beda dari leet-date/
   overeats Task 6/8). Sesuai instruksi infra: dipilih pola **attach ke `forcad_default`**, BUKAN
   VM.
7. **Recon manual 3 sesi** (`python3` socket mentah dari laptop, `192.168.43.136:6767` reachable
   langsung) — lihat §Transkrip. Ini yang membongkar seluruh protokol nyata dan menjungkirbalikkan
   beberapa asumsi brief.
8. Tulis `checkers/enowars10/superregister/checker.py`, uji cepat lokal (venv `.venv-eno` yg
   sudah punya `checklib`) langsung ke `192.168.43.136:6767` untuk iterasi tanpa perlu
   docker-cp berulang ke celery.
9. Deploy ke celery (`~/adlab/forcad/checkers/eno10_superregister/checker.py` di host, otomatis
   ter-mount ke `/checkers/eno10_superregister/` di kontainer `forcad-celery-1`; `chmod +x`).
   `docker network connect forcad_default superregister-superregister_server-1` supaya bisa
   diakses dari `forcad-celery-1`, dapat IP `192.168.0.17`.
10. Gate 5 kasus wajib dari dalam `forcad-celery-1` (user exec default = `nobody`, dicek `id`).
    Semua 5 LOLOS pada percobaan checker final (lihat §Gate).
11. Teardown: `docker compose down -v` di server (container+network project dihapus; RAM kembali
    ke baseline ~6.9Gi available). Bersihkan file scratch `/tmp` di server.
12. Commit **hanya** `checkers/enowars10/superregister/checker.py` (`be13dc8`). Config
    (`config.enowars10.yml`) **TIDAK disentuh**, **TIDAK ada engine round** — sesuai resolusi
    eksplisit ambiguitas brief Step 4 (ditunda, gate menggantikannya sbg bukti).

## Transkrip protokol yang dikonfirmasi (byte-for-byte, dari recon live)

Semua transkrip di bawah dari koneksi socket Python mentah ke `192.168.43.136:6767` (sebelum
`superregister` di-attach ke `forcad_default`; port 6767 saat itu masih host-published).

**Banner awal** (menjawab `check()`):
```
b'\n=== SUPERREGISTER Vehicle Management System ===\nCommands: Login, Register, Exit\n> '
```

**Register** (`register` → 3 prompt terpisah, BUKAN `Register <user> <pass>` satu baris seperti
draf brief):
```
>>> register
<<< 'Choose a Username: '
>>> <username>
<<< 'Choose a Password: '
>>> <password>
<<< 'Enter your Home Address: '
>>> <alamat bebas>
<<< '\nRegistration successful! You may now login.\n\n=== SUPERREGISTER ... ===\n...\n> '
```

**Login** (`login` → 2 prompt terpisah, BUKAN `Login <user> <pass>` satu baris):
```
>>> login
<<< 'Username: '
>>> <username>
<<< 'Password: '
>>> <password>
<<< '\nLogin successful! Clearance Level: 1\n\nMOTD: ...\n\n=== MAIN TERMINAL ===\n...\n> '
    (gagal: '\nInvalid credentials.\n\n=== SUPERREGISTER ... ===\n...\n> ' — balik ke banner
    pra-auth, BUKAN Main Terminal)
```

**Add** (command sebenarnya `add`, BUKAN `AddVehicle`; satu baris CSV, dan — temuan PALING
PENTING — **TIDAK ADA prompt re-auth password, dan TIDAK ADA id kendaraan di respons**):
```
>>> add
<<< 'Enter details (Make,Model,Year,Color[,VIN,Note]):\n> '
>>> Make,Model,Year,Color,VIN,Note-berisi-flag
<<< 'Vehicle added successfully.\n\nMOTD: ...\n\n=== MAIN TERMINAL ===\n...\n> '
```
Dicoba eksplisit mengirim ulang password setelah ini (menduga ada prompt re-auth tersembunyi
spt string binary "Re-enter password to add a vehicle:") — hasilnya `"Invalid command."`,
membuktikan prompt itu **tidak pernah muncul** untuk user clearance biasa di alur `add`.

**Search** (dipakai utk menggali id kendaraan balik, krn `add` tak mengembalikannya):
```
>>> search <make unik yg kita set saat add>
<<< '\n--- Search Results ---\n[<id>] <make> <model>\n\nMOTD: ...\n> '
    (tak ketemu: '\n--- Search Results ---\n\nMOTD: ...\n> ' — tanpa baris `[id] ...`)
```

**ReadNote** (`readnote <VehicleIDMilikSendiri> <VehicleIDTarget>` satu baris; DUA angka
sama-sama vehicle id, TIDAK ADA entitas "note" terpisah — lihat §Skema DB):
```
>>> readnote <vid> <vid>              (baca note milik sendiri)
<<< '\n[Maintenance Note]: <isi note>\n\nMOTD: ...\n> '
>>> readnote <vid-bukan-milik> <apa saja>
<<< 'Authorization failed for your vehicle.\n\nMOTD: ...\n> '
```

**Exit pra-auth** (dipakai `check()` sbg bukti liveness kedua selain banner):
```
>>> exit
<<< 'Goodbye.\n'
```

## Koreksi menyeluruh terhadap brief (dikonfirmasi live, bukan tebakan `strings`)

1. **Register butuh TIGA field berurutan** (Username, Password, **Home Address** — brief tak
   menyebut alamat sama sekali), masing-masing prompt terpisah — bukan `Register <user> <pass>`
   satu baris.
2. **Login butuh DUA prompt terpisah** (Username lalu Password) — bukan `Login <user> <pass>`
   satu baris.
3. **Command bikin kendaraan adalah `add`, bukan `AddVehicle`.** Ditemukan dari daftar menu Main
   Terminal (`- Add`), dikonfirmasi live command lowercase `add` diterima.
4. **PALING PENTING — brief mengasumsikan respons `add` mengandung id kendaraan yang bisa
   di-regex (`_parse_ids`). Ini SALAH.** Respons live persis `"Vehicle added successfully."`
   TANPA id apa pun. String binary `"Added new vehicle: "` yang tampak menjanjikan di `strings`
   ternyata bukan echo ke klien — itu teks LOG internal (dikonfirmasi lewat command `history`:
   `[User N] Added new vehicle: <MAKE>`, isinya MAKE bukan angka, sehingga TAK BISA dipakai
   menggali id juga). Solusi: `add` diberi field **Make** yang unik (`A.rand_username()`), lalu
   `search <make>` dipanggil setelahnya — responsnya `[<id>] <make> <model>`, dari situ id
   digali via regex yang diikat ke make persis milik kita (`_parse_id`), bukan regex spekulatif
   generik seperti draf brief.
5. **Tidak ada prompt re-auth password untuk `add`** (walau string `"Re-enter password to add a
   vehicle: "` ada di binary) — dibuktikan aktif dgn mengirim password setelah `add` sukses dan
   mendapat `"Invalid command."` (bukti server sudah kembali ke Main Terminal, menunggu command
   baru, bukan menunggu password).
6. **Skema DB dibaca dari `strings` (literal SQL `CREATE TABLE`) TAK PUNYA tabel `notes`
   terpisah** — `maintenance_note` adalah KOLOM pada tabel `vehicles`. Jadi "ReadNote
   [Vehicle ID] [Note ID]" sebenarnya "ReadNote [id kendaraan MILIK SENDIRI, utk otorisasi]
   [id kendaraan TARGET, notenya dibaca]" — dua-duanya sama-sama vehicle id. Dikonfirmasi live
   lewat query yang dibaca dari `strings`: `SELECT id FROM vehicles WHERE id=? AND user_id=?`
   (otorisasi via ARG PERTAMA) diikuti `SELECT maintenance_note FROM vehicles WHERE id=?` (baca
   via ARG KEDUA, **tanpa filter user_id**). Ini IDOR by design (siapa saja bisa baca note
   kendaraan siapa saja, asal tahu SATU id kendaraan miliknya sendiri utk lolos cek pertama) —
   dikonfirmasi empiris: `readnote <vid-milik-sendiri> <vid-milik-user-lain>` BERHASIL membaca
   note user lain. **Checker ini sengaja TIDAK bergantung pada vuln itu** untuk round-trip-nya
   sendiri — `put()`/`get()` selalu memakai vid milik sendiri utk KEDUA argumen, jalur yang sah
   tanpa menyentuh IDOR sama sekali. Konsekuensi desain: state cukup simpan **satu** id (`v`),
   bukan pasangan `(v, n)` terpisah seperti draf brief — field "n" would be redundant/misleading
   karena entitas note independen memang tidak ada.
7. **Semua respons "selesai" (baik sukses/gagal, baik pra-auth maupun Main Terminal) diakhiri
   byte literal `"> "`**, dan tak ada teks isi (menu/pesan) yang kebetulan mengandung `"> "` di
   tengah. Ini dipakai sbg delimiter `recv_until` universal SETELAH tahap prompt-field individual
   (Username/Password/Choose a.../Enter your...) yang harus dikenali via teks prompt-nya sendiri
   persis (delimiter generik spt `b": "` terbukti berbahaya — akan berhenti kepagian di tengah
   teks spt `"Clearance Level: "` dan bikin desync, persis peringatan brief soal `recv(N)` tetap
   berlaku juga utk delimiter yg terlalu generik).

## Keputusan infra: server + `forcad_default`, bukan VM

`docker-compose.yml` map `"6767:6767"` dan biner benar-benar `listen()` di 6767 di dalam
kontainer (bukan cuma host-publish ke port internal lain, kontras dgn leet-date/overeats Task
6/8) — jadi pola "attach kontainer ke `forcad_default`, gate ke IP kontainer" berlaku bersih di
sini, TANPA perlu VM tim. `docker network connect forcad_default
superregister-superregister_server-1` → IP `192.168.0.17` di jaringan itu, dipakai sbg target gate
`docker exec forcad-celery-1 .../checker.py <action> 192.168.0.17 ...`.

## Build — tanpa patch

`Dockerfile`: `FROM python:3-alpine`, `apk add g++ sqlite-dev openssl-dev`, `COPY bin/
/service/`, `ENTRYPOINT ["/entrypoint.sh"]`. **Tidak ada `RUN --mount=type=cache` sama sekali** —
keterbatasan "BuildKit tak tersedia di server utama" (dicatat di brief global) tidak relevan
untuk service ini. `docker compose build` dijalankan apa adanya di server (`192.168.43.136`),
sukses bersih (log lengkap: instalasi apk paket → 5 langkah Dockerfile → "Successfully built").
**Tidak ada diff patch build untuk dicatat** — sama seperti leet-date (Task 8), berbeda dari
greple/flagdrive/funsplash (Task 2/4/7) yang butuh patch server-only.

## `LineClient` — memadai penuh untuk protokol ini, tanpa gap

Dipakai: `sendline(str)` (auto-encode + `\n`), `recv_until(delim: bytes)` (buffer internal
`self.buf` menangani sisa data lintas panggilan — persis semantik yang dibutuhkan protokol
prompt-demi-prompt ini), `close()`. **Tidak dipakai**: `recv(n)` fixed-size sama sekali — checker
final murni pakai `recv_until` di setiap langkah (persis anjuran brief "prefer reading until a
known prompt or delimiter"), termasuk utk banner awal dan respons `exit` pra-auth.

Perilaku yang diverifikasi cocok kebutuhan:
- Timeout eksplisit (`timeout=10.0` default constructor, diwariskan ke `socket.settimeout`) —
  dicek langsung: target host unreachable (`10.255.255.1`, blackhole) menghasilkan
  `TimeoutError('timed out')`; target host reachable-tapi-port-tertutup menghasilkan
  `ConnectionRefusedError`; target host **benar-benar tak ada rute** (dipakai di gate resmi,
  `192.168.0.250` di jaringan `forcad_default`) menghasilkan `OSError(113, 'No route to
  host')`. **Ketiganya** ditangkap oleh `A.status_for()` sbg `Status.DOWN` (via cabang
  `ConnectionError`/`TimeoutError`/`OSError` generik) — semuanya sensible, tak ada yang perlu
  penanganan tambahan.
- `recv_until` yang delimiter-nya tak pernah ketemu (mis. koneksi ditutup paksa di tengah)
  mengembalikan apa pun yang terkumpul di buffer tanpa hang — sifat graceful ini tak pernah
  ter-trigger di gate (semua respons live selalu berakhir rapi dgn delimiter yang diharapkan),
  tapi dikonfirmasi dari membaca kode `_lib` (bukan diuji langsung).

**Tidak ada gap.** Satu observasi kecil (bukan gap fungsional): `LineClient` tak punya method utk
mengganti timeout per-langkah setelah konstruksi (mis. banner cepat vs operasi lambat) — kalau
suatu saat perlu, `c.s.settimeout(...)` bisa dipanggil manual krn `s` adalah atribut publik, tapi
protokol `superregister` tak butuh ini sama sekali (semua langkah cepat & seragam).

## Gate — lima kasus wajib

Dijalankan dari `forcad-celery-1` (`docker exec`, user `nobody` — dicek `id` →
`uid=65534(nobody) gid=65534(nogroup)`), target `192.168.0.17:6767` (IP `forcad_default` milik
kontainer service):

```
1. check (live)                                                    → 101
2. put   (live)                                                     → 101
   stdout (flag_id) = {"u":"EagerCedar6260","p":"hoTiBwGNPco2v3CR","v":"5"}
3. get   (flag_id di atas, flag sama "GATEFLAG_9f8e7d6c=")          → 101
4. get   (state well-formed, kredensial SAMA/nyata, v="8675309" —
          vehicle id tak ada)                                       → 102
   pesan: "flag tak ada di note"
   detail: contains assertion failed: b'GATEFLAG_9f8e7d6c=' not in
           b'Authorization failed for your vehicle.\n\n...'
5. check (host tak ada rute, 192.168.0.250 di forcad_default)       → 104
   detail: OSError(113, 'No route to host')
```

Sebelum gate resmi ini, seluruh 5 kasus (plus kasus tambahan: login salah password → **103
MUMBLE**, bukan CORRUPT — mengonfirmasi kepatuhan pada aturan "login gagal di `get()` = MUMBLE")
sudah diuji lebih dulu **lokal** (venv `.venv-eno` di laptop langsung ke `192.168.43.136:6767`,
sebelum service di-attach `forcad_default`) untuk iterasi cepat tanpa bolak-balik `docker cp` ke
celery. Draf checker final LANGSUNG lolos gate resmi tanpa iterasi ulang setelah pindah ke
celery — konsisten krn protokol/parsing sudah divalidasi habis di tahap lokal.

Setelah gate: `docker compose down -v` di server (container + network project superregister
dihapus bersih, dicek `docker ps` kosong utk `superregister`). RAM kembali ke ~322Mi
used-baseline / 6.9Gi available (sama seperti sebelum service dinaikkan).

## checker_timeout: 20 (nilai brief) — dikonfirmasi memadai, tidak diubah

`put()` melakukan ~11 langkah recv_until berurutan (banner + register×4 + login×3 + add×2 +
search×1); `get()` 3 (banner + login×2 + readnote×1... tepatnya banner+login(2 prompt+1 hasil)+
readnote = 5); `check()` 2 (banner + exit). Semua langkah di gate live selesai sub-detik secara
agregat (seluruh sesi `put` dari koneksi sampai `cquit` terasa instan tanpa jeda yang terlihat).
`checker_timeout: 20` dari brief memberi margin besar dibanding observasi aktual — **tidak
diusulkan perubahan**. Catatan teoretis (bukan yang teramati): dgn timeout LineClient
default 10 detik per operasi, SATU langkah yang hang akan menghabiskan setengah budget sebelum
`TimeoutError` keluar bersih sbg DOWN — ini sudah cukup aman (proses keluar jauh sebelum 20 detik
habis), dan hanya jadi risiko kalau BANYAK langkah berbeda di action yang SAMA sama-sama hang
mendekati 10 detik sebelum akhirnya gagal/berhasil, skenario yang tak pernah teramati di service
ini (baik pada uji lokal maupun gate resmi).

## Reaper / TTL: TIDAK DITEMUKAN mekanisme time-based — beda dari 4 service lain

Dari `strings` biner ditemukan mekanisme **prune berbasis KAPASITAS** (bukan waktu):
```
DELETE FROM vehicles WHERE id NOT IN (SELECT id FROM vehicles ORDER BY id DESC LIMIT 10000);
DELETE FROM users WHERE id NOT IN (SELECT id FROM users ORDER BY id DESC LIMIT 10000) AND id > 3;
DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 10000);
```
dipicu oleh log tag `"[TIMER] Running scheduled database prune..."` (ada juga
`"[TIMER] Successfully truncated fake_environ.txt."` utk file lain yang tak terkait
vehicle/note). Ini **bukan** TTL per-baris (tidak ada `created_at < NOW() - INTERVAL ...` spt
d3pl0y/flagdrive/overeats/leet-date) — melainkan "simpan 10000 kendaraan/user/log TERBARU,
buang sisanya". Baris kendaraan milik flag yang baru dibuat TIDAK akan hilang sampai lebih dari
10.000 kendaraan BARU dibuat setelahnya — jauh lebih longgar daripada TTL 12-15 menit yang
dilaporkan Task 3/4/6/8. **Interval TIMER-nya sendiri (setiap berapa detik/menit prune ini
dijalankan) TIDAK saya konfirmasi secara live** — sesi saya (~20 menit interaksi aktif) tidak
menghasilkan log `[TIMER]` yang teramati (log yang saya cek hanya startup: "Database tables
ensured.", "Initial data seeded successfully.", pesan kunci VM, "CTF Vehicle Server listening
..." — tak sempat menunggu cukup lama utk melihat siklus TIMER pertama, dan servicenya sudah
diturunkan setelah gate). **Kesimpulan yang bisa dipertanggungjawabkan**: superregister TIDAK
memaksakan batas `round_time × flag_lifetime` yang ketat seperti 4 service lain — batasnya
berbasis volume data (>10.000 kendaraan baru), praktis tak akan tercapai dalam siklus
checker normal. Tidak ada nilai menit yang perlu dicatat utk `config.enowars10.yml` nanti.

## Yang TIDAK diverifikasi / di luar cakupan

- **Interval TIMER prune yang sesungguhnya** (lihat §Reaper di atas) — hanya diverifikasi
  keberadaan mekanismenya (dan sifatnya kapasitas-bukan-waktu) via `strings`, bukan diamati
  langsung siklusnya.
- **MUMBLE saat service hidup-tapi-salah** (mis. banner ada tapi bukan SUPERREGISTER) dan
  **CORRUPT saat flag ADA tapi DIUBAH** (mis. lawan menimpa `maintenance_note` kendaraan korban
  — service ini TIDAK punya endpoint edit yang membiarkan pihak lain menimpa note orang lain
  secara langsung tanpa login sbg pemilik, jadi skenario "flag diubah lawan" kurang relevan
  dibanding kasus 8 service HTTP lain) — sama seperti dicatat lintas-task di Task 5/8, tidak
  diuji sbg kasus gate tambahan, hanya lewat pembacaan struktur SQL (`ReadNote` melakukan
  `SELECT` langsung tiap panggilan, jadi kalau isi `maintenance_note` berubah di DB, `get()`
  akan otomatis membaca versi terbaru dan flag lama akan CORRUPT dgn benar).
- Fitur lain servis yang jauh lebih besar dari cakupan brief (dibaca sekilas via `strings`,
  TIDAK disentuh checker sama sekali): `Edit`, `Remove`, `List`, `Diagnostic`, `ReadLog`,
  `FirmwareDump`, `History`, `Settings` (`Password`/`Clearance`), dan seluruh subsistem
  "secure admin login" berbasis DHE/Ed25519 (`get_identity`, `dhe_init`, `dhe_deposit`,
  `get_admin_challenge`, `secure_admin_login`) yang tampaknya jalur bootstrap admin/rotasi
  password tim via key exchange — sama sekali di luar kontrak PUT/GET flag (Register→Add→
  ReadNote), tidak diuji.
- IDOR (`readnote <milik-sendiri> <milik-orang-lain>`) dikonfirmasi ADA dan berfungsi
  (§Koreksi #6), tapi checker sengaja tidak bergantung padanya — jadi tidak ada assert eksplisit
  atas perilaku IDOR itu sendiri di checker final (hanya dipakai sbg pemahaman protokol saat
  recon).
- Perilaku checker di bawah beban paralel (banyak `put`/`get` bersamaan ke service yang sama) —
  gate hanya menguji sekuensial.
- Config (`config.enowars10.yml`) dan status `UP` via engine round — sengaja tidak dikerjakan,
  sesuai resolusi ambiguitas brief Step 4.

## Concerns

1. **Tidak ada concern build/infra.** Build bersih tanpa patch, topologi `forcad_default`
   berfungsi langsung tanpa perlu VM tim.
2. **Field CSV `add` tak diuji secara eksplisit terhadap flag yang (secara hipotetis) mengandung
   koma.** Format flag ForcAD standar tidak memakai koma, dan `Note` adalah field TERAKHIR di CSV
   — kalaupun parsing service naif (split-per-koma tanpa batas), hanya berisiko kalau flag itu
   sendiri mengandung `,` literal, yang di luar kendali checker dan di luar observasi format
   flag yang lazim. Tidak diuji langsung krn tak ada cara mengontrol format flag asli platform
   dari sisi checker.
3. **Interval TIMER prune tidak terkonfirmasi live** (lihat §Reaper) — risiko rendah krn sifatnya
   kapasitas bukan waktu, tapi dicatat sbg gap pengetahuan yang jujur, bukan diasumsikan nol
   dampak.
4. Konsisten dgn seluruh sibling checker (Task 3/4/5/6/8): `flag_id` yang BUKAN JSON sama sekali
   (bukan "JSON valid tapi id tak ada") akan jatuh ke `status_for(ValueError) = MUMBLE`
   (103), bukan CORRUPT (102) — perilaku `decode_state`/harness, bukan cacat checker ini. Tidak
   masalah di produksi krn `flag_id` ForcAD selalu berasal dari `put()` sebelumnya (selalu JSON
   valid). Kasus gate "bogus flag_id" resmi yang dipakai (JSON valid, kredensial nyata, vehicle
   id tak ada) sudah sesuai arahan task ini secara eksplisit.

## File yang relevan

- `checkers/enowars10/superregister/checker.py` (repo, 200 baris) — **satu-satunya file yang
  di-commit** untuk task ini, commit `be13dc8`.
- `~/adlab/eno10/superregister/` di server (`192.168.43.136`) — rsync source, **tanpa
  modifikasi** (tak ada patch build yang perlu dipertahankan).
- `forcad-celery-1:/checkers/eno10_superregister/checker.py` (host source:
  `~/adlab/forcad/checkers/eno10_superregister/checker.py`) — dibiarkan terpasang (mode 755,
  owner uid 1000, dicek `nobody` bisa baca+eksekusi), sama seperti preseden sibling lain.
- Service superregister **diturunkan** (`docker compose down -v`) setelah gate — tidak dibiarkan
  jalan, sesuai batasan RAM server.
