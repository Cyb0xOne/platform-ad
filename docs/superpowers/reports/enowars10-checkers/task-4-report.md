# Task 4 Report: Checker `flagdrive` (:4859) — file store, token multipart

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(flag_id bogus)=102`, `check(host mati)=104`.
Commit: `315b437` — `feat(eno10): checker flagdrive (file store) + gate lolos` (branch `enowars10-checkers`).

Servis Rust ini **butuh 2 patch build di salinan server** (BuildKit cache-mount tak tersedia +
bug genuine `tailwind-css` href salah target) sebelum bisa dibangun sama sekali — beda dari
d3pl0y (Task 3) yang mulus tanpa patch, tapi sejalan dgn greple (Task 2, 2 patch Zig). Tidak ada
BLOCKED — semua bisa diselesaikan dgn effort wajar dan didokumentasikan penuh di bawah.

---

## Ringkasan alur

1. Baca brief + baca ULANG source asli nyata (`main.rs`, `shared/src/lib.rs`, `auth.rs`,
   `api_routes/{register,login,token,files}.rs`, `crypto.rs`, `database/{core,users,files}.rs`,
   migrasi SQL) sebelum menulis checker — brief eksplisit bilang kontrak field derived dari
   recon statis dan 3 task sebelumnya semua meleset di titik berbeda.
2. Tulis `checkers/enowars10/flagdrive/checker.py` dari template brief + koreksi (lihat bawah).
3. rsync source `flagdrive/` dari laptop ke server (`~/adlab/eno10/flagdrive/`, 376K, 61 file).
4. Tulis `docker-compose.override.yml` TANGAN LANGSUNG (bukan lewat `deploy/enowars10-deploy.sh`)
   menempel HANYA `flagdrive-service` (bukan `flagdrive-db`) ke `forcad_default` — proaktif
   menghindari bug idempotency-guard skrip yg sudah didokumentasikan Task 3 (skrip tak disentuh,
   tetap di luar scope).
5. `docker compose up -d --build` #1 **gagal** di step frontend (`trunk build`): tailwind-css
   asset tak ketemu filenya. Diagnosis dari source + dokumentasi resmi Trunk (lihat bawah) →
   patch `frontend/index.html` (server copy saja) → rebuild #2 (memakai layer cache dependency
   yg sudah ada) → **sukses**, kedua container `Up`.
6. Reachability + verifikasi bentuk request MANUAL via curl dari DALAM container celery (vantage
   point sama dgn gate) SEBELUM menjalankan checker resmi: health, register, login, upload
   (dgn kedua varian visibility — huruf kecil brief DAN huruf besar terkoreksi), download (id
   nyata DAN id bohongan) — semua dicocokkan ke `checker.py` sebelum gate resmi.
7. Deploy checker ke celery (host path langsung `~/adlab/forcad/checkers/eno10_flagdrive/`, mode
   755), diff eksplisit vs repo lokal (identik), sanity-import di dalam container.
8. Gate 5-langkah — semua lolos exit code yang diminta.
9. Teardown (`docker compose down -v`), verifikasi container hilang, `forcad_default` balik ke
   15 anggota, memory available balik ke/atas baseline.
10. Commit HANYA `checkers/enowars10/flagdrive/checker.py`. `forcad/config.enowars10.yml` TIDAK
    disentuh, TIDAK ada ronde engine dijalankan (sesuai instruksi override task).

---

## Perubahan bentuk request terhadap brief

Berbeda dari greple/d3pl0y (semua 3 field yang salah adalah prefix rute / bentuk body), brief
Task 4 **benar** untuk rute dan nama field multipart — hanya SATU nilai (`visibility`) yang
salah, tapi dampaknya fatal (upload SELALU gagal). Dikonfirmasi silang: baca source Rust +
curl manual dari dalam celery.

### 1. KRITIS — nilai `visibility` harus `"Private"` (kapital), bukan `"private"`

`shared/src/lib.rs:3-9`:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FlagDriveFileVisibility {
    Private,
    Public,
    Following,
    Followers,
}
```
Tidak ada `#[serde(rename_all = ...)]` di mana pun di codebase (dicek via
`grep -rn "rename_all" --include="*.rs" .` — nihil) → representasi JSON enum ini adalah nama
varian Rust APA ADANYA (huruf besar di depan), BUKAN `"private"` seperti tebakan brief.

`shared/src/lib.rs:124-132` — `visibility` di `UploadMetadata` TIDAK punya `#[serde(default)]`
(field wajib untuk deserialisasi berhasil):
```rust
pub struct UploadMetadata {
    pub token: String,
    #[serde(default)]
    pub key: Option<String>,
    pub visibility: FlagDriveFileVisibility,   // <- wajib, tanpa default
    #[serde(default)]
    pub backup: Option<bool>,
}
```

`backend/src/api_routes/files.rs:80-91` — kalau `visibility` tak cocok varian manapun, SELURUH
parse `UploadMetadata` gagal, dan kegagalan itu DIAM-DIAM ditelan:
```rust
"json" => {
    if let Ok(bytes) = field.bytes().await {
        if let Ok(payload) = serde_json::from_slice::<UploadMetadata>(&bytes) {
            token = payload.token;   // <- hanya di-assign kalau parse SUKSES
            ...
        }
    }
}
```
`token` lokal (files.rs:62, `let mut token = String::new();`) tetap kosong walau token yang
dikirim di JSON valid → files.rs:96 (`if token.is_empty() || ...`) → 400
`"Token, name, and file content are required"`.

**Dikonfirmasi EMPIRIS lewat curl dari dalam container celery** (bukan cuma baca source):
```
$ curl -X POST http://192.168.0.17:4859/api/file/upload -F "file=@/tmp/testflag.txt;filename=f.txt" \
    -F 'json={"token":"<token-valid>","visibility":"private"};type=application/json'
{"error":"Token, name, and file content are required"}   http_code=400

$ curl ... -F 'json={"token":"<token-valid-sama>","visibility":"Private"};type=application/json'
{"file_id":5351753945584915633}   http_code=201
```
Token PERSIS SAMA di kedua percobaan — satu-satunya perbedaan adalah huruf `visibility`. Ini
membuktikan kausalitas langsung, bukan kebetulan.

Konfirmasi silang tambahan (consumer nyata lain dari enum yang sama):
`frontend/src/components/upload_modal.rs:154-157` memakai label persis
`"Public"`/`"Following"`/`"Followers"`/(default)`"Private"` untuk field yang sama.

Checker `put()` dikoreksi jadi `json.dumps({"token": token, "visibility": "Private"})`.

### 2. Verifikasi tambahan (bukan koreksi, BENAR dari awal) — didokumentasikan supaya jelas mana yang sudah tervalidasi

- **Prefix rute**: `backend/src/main.rs:77-103` — `/api/health`, `/api/auth/register`,
  `/api/auth/login`, `/api/file/upload`, `/api/file/download/{file_id}` — PERSIS sama dgn brief.
  Beda dari Task 2/3 di mana prefix `/api` justru HILANG di tebakan brief.
- **Nama field multipart**: `backend/src/api_routes/files.rs:70-91` — `match name_str.as_str()`
  cocok persis `"file"` (bagian file, filename dari `field.file_name()`) dan `"json"` (bagian
  metadata teks) — sama dgn brief.
- **Bentuk respons login/register**: `AuthResponse { token, username }` (`shared/src/lib.rs:48-52`,
  dipakai `register.rs:62-72` & `login.rs:55-65`) — `r.json().get("token")` brief sudah benar.
- **Nama field file id**: `UploadResponse { file_id: u64 }` (`shared/src/lib.rs:134-137`) — persis
  `"file_id"`, tebakan utama brief benar (fallback `.get("id")` di kode brief jadi dead code,
  dibiarkan apa adanya karena tak berbahaya).

Semua di atas dikonfirmasi ganda: baca source DAN curl manual dari dalam celery sebelum menulis
gate resmi (lihat bagian "Verifikasi manual" di evidence).

### 3. Perbaikan (bukan koreksi bug brief) — cek byte, bukan teks, di `get()`

`backend/src/api_routes/files.rs:381-386` — respons sukses endpoint download:
```rust
Response::builder()
    .status(StatusCode::OK)
    .header("content-type", "application/octet-stream")
    .header("content-disposition", content_disposition)
    .body(Body::from(returned_content))
```
Konten balikan eksplisit `application/octet-stream` (byte file mentah), BUKAN teks/HTML seperti
greple/d3pl0y. Brief Step 1 memakai `assert_in(flag, r.text, ...)` mengikuti pola sibling —
`r.text` di `requests` untuk content-type non-teks jatuh ke deteksi charset otomatis
(`apparent_encoding`), yang KEMUNGKINAN BESAR tetap benar untuk flag ASCII murni tapi tidak
dijamin. Diganti jadi `self.assert_(flag.encode() in r.content, ...)` — cek di level byte,
tak bergantung pada tebakan charset sama sekali. Dikonfirmasi round-trip byte-exact via curl
manual (lihat evidence) sebelum dipakai di checker resmi.

---

## Detail arsitektur flagdrive (konteks utk task berikutnya bila flagdrive masuk roster resmi)

- **Enkripsi AES-256-GCM per file** (`backend/src/crypto.rs`): key diturunkan dari
  `derive_aes_key(user_key, file_key, server_key)` (custom bit-mixing, bukan HKDF standar), IV
  dari `construct_iv(username)` (deterministik per-username, SHA-256 based), AAD = iv+username.
  Checker TIDAK mengirim `key` (opsional, default kosong) → `is_protected=false` di DB
  (`files.rs:187/196`) → download tak perlu cocokkan key apa pun, akses cukup lewat kepemilikan
  (`file.owner == username` dari token, `files.rs:297`). Round-trip byte-exact dikonfirmasi
  empiris (curl upload "TESTFLAGCURLROUNDTRIP789" → download → byte identik).
- **`id` file** dibuat via `rand::rng().random::<u64>()` (`files.rs:94`), disimpan ke kolom
  `BIGINT` via cast `id as i64` (reinterpretasi bit dua kali — konsisten PP/GET, tak masalah).
  Ruang ID penuh 64-bit → id kecil seperti `"1"` nyaris pasti belum dipakai, dipakai sbg
  flag_id "bogus" yg valid-JSON tapi nonexistent (lihat gate §4 di bawah).
- **Reaper 12 menit**: `main.rs:67-75` menjalankan task background tiap 60 detik memanggil
  `delete_old_data(pool, 12*60)` (`database/core.rs:20-37`) — DELETE users lebih tua dari 12
  menit (CASCADE ke files/tokens/follows lewat FK). **Pola identik dgn d3pl0y (Task 3)** — user
  baru per-PUT (sudah jadi desain checker ini) menghindari masalah ini, tapi relevan utk
  `config.enowars10.yml` nanti: `round_time × flag_lifetime` sebaiknya « 720 detik. Tidak ada
  tindakan diambil sekarang (config sengaja ditunda, sama seperti Task 3).
- **`check_user_password`** (`database/users.rs:51-63`) membandingkan password PLAINTEXT
  (`user_password == password`) — tak ada hashing. Bukan concern checker (tak ada dampak ke
  gate), dicatat murni sbg observasi arsitektur.

---

## Bug build ditemukan (SERVICE, bukan checker) — dipatch di SALINAN SERVER SAJA

Sejalan dgn precedent Task 2 (greple/Zig, 2 patch) — laptop source (`~/workspaces/cylab/ctf/...
/flagdrive/`) **TIDAK disentuh sama sekali**, hanya `~/adlab/eno10/flagdrive/` (server) dipatch.

### A. `RUN --mount=type=cache` butuh BuildKit murni — tak tersedia di server ini

`Dockerfile` asli punya 4 blok `RUN --mount=type=cache,id=...,target=...` (cook-frontend,
cook-backend, builder-frontend, builder-backend). Log build #1:
```
level=warning msg="Docker Compose requires buildx plugin to be installed"
```
(peringatan ini SENDIRI tidak fatal — compose fallback ke classic builder). **Yang jadi
soal** adalah kalau saja Dockerfile SAMPAI ke baris `--mount`, itu akan gagal fatal di classic
builder (persis catatan Task 2). Untungnya build kali ini gagal DULUAN di step trunk (bug B di
bawah) sebelum sempat membuktikan itu — tapi utk berjaga, kedua baris `--mount=type=cache,...`
di keempat blok RUN dihapus proaktif di salinan server (cache mount murni optimisasi rebuild,
bukan kebutuhan fungsional) SEBELUM percobaan build pertama. Build #1 lolos step ini tanpa
keluhan BuildKit sama sekali (build gagal di step lain, bug B) — mengonfirmasi patch ini
memang perlu & bekerja.

### B. Genuine bug: asset `tailwind-css` menunjuk ke path OUTPUT, bukan SOURCE

Log build #1:
```
Step 27/44 : RUN cd frontend && trunk build --release --quiet && cd ..
ERROR error from build pipeline
Caused by:
    0: error getting canonical path for "/ctf/service/frontend/style/tailwind.css"
    1: No such file or directory (os error 2)
```

`frontend/index.html:8` (asli): `<link data-trunk rel="tailwind-css" href="style/tailwind.css" />`.

Dicek ke dokumentasi resmi Trunk (trunkrs.dev/trunk-rs.github.io, via web search — WebFetch
langsung ke domain itu diblok 403 tapi cuplikan hasil pencarian & repo contoh cukup jelas):
`rel="tailwind-css"` adalah fitur NATIF Trunk — `href` harus menunjuk ke file CSS SUMBER berisi
direktif tailwind (`@import "tailwindcss";` dst.), dan **Trunk SENDIRI yang memanggil binary
`tailwindcss`** utk mengompilasinya; ia TIDAK mengharapkan file yang sudah jadi/di-precompile.

Source tailwind asli proyek ini ada di `frontend/src/styles/tailwind.css` (sintaks Tailwind v4:
`@import "tailwindcss";` + `@theme{...}` + `@layer base{...}`) — BUKAN di `style/tailwind.css`
(path yang di-refer index.html, dan yang di-`.gitignore`-kan sbg direktori OUTPUT:
`.gitignore` baris `frontend/style/`).

`frontend/Trunk.toml:9-13` punya `[[hooks]]` custom (`stage = "build"`) yang manual menjalankan
`tailwindcss -i src/styles/tailwind.css -o style/tailwind.css` — niatnya menghasilkan file yang
di-refer href. TAPI menurut dokumentasi Trunk, hook `stage = "build"` "executes in parallel with
all of the existing asset pipelines" — tidak ada jaminan urutan thd asset pipeline native
`tailwind-css` milik Trunk sendiri, yang tampaknya me-resolve/canonicalize `href`-nya SEGERA
(kalah balapan tiap kali, bukan flaky — build #1 gagal deterministik di percobaan pertama).

**Fix** (`frontend/index.html` salinan server SAJA, baris 8):
```html
<link data-trunk rel="tailwind-css" href="src/styles/tailwind.css" />
```
Menunjuk langsung ke file sumber asli; pipeline native Trunk yang mengompilasi (binary
`tailwindcss` sudah terpasang di stage `toolchain` Dockerfile). Hook custom di `Trunk.toml`
DIBIARKAN apa adanya (jadi dead code yang menghasilkan `style/tailwind.css` tak terpakai —
tidak berbahaya, tidak disentuh supaya perubahan seminimal mungkin). Build #2 (memakai cache
layer dependency dari build #1 yang gagal HANYA di step frontend) sukses penuh; berhenti hanya
di ulang-kompilasi frontend+backend nyata, bukan re-download/re-compile seluruh dependency Rust.

**Tidak diperbaiki**: `deploy/enowars10-deploy.sh` (bug override-generation dari Task 3) — tidak
tersentuh sama sekali di task ini karena saya menulis `docker-compose.override.yml` tangan
langsung dari awal, sengaja menghindari skrip tsb (bukan karena ketemu masalah baru).

---

## Evidence gate (exact commands + output)

Server: `reky@192.168.43.136`. Service `flagdrive` di HOST (bukan VM tim), network
`forcad_default`, IP container `192.168.0.17:4859` (IP kebetulan sama dgn d3pl0y di Task 3 —
d3pl0y sudah di-teardown, alokasi ulang oleh Docker, bukan konflik).

### Build
```
$ cd ~/adlab/eno10/flagdrive && docker compose up -d --build     # percobaan #1
...
Step 27/44 : RUN cd frontend && trunk build --release --quiet && cd ..
ERROR error getting canonical path for "/ctf/service/frontend/style/tailwind.css": No such file or directory
COMPOSE_UP_EXIT=1

# patch frontend/index.html (server copy) -> href="src/styles/tailwind.css"

$ docker compose up -d --build                                   # percobaan #2
...
Successfully tagged flagdrive-flagdrive-service:latest
 Container flagdrive-flagdrive-db-1 Started
 Container flagdrive-flagdrive-service-1 Started
COMPOSE_UP_EXIT=0
```

### Reachability + verifikasi manual (dari dalam celery, SEBELUM gate resmi)
```
$ docker exec $C curl -m5 http://192.168.0.17:4859/api/health
{"status":"ok","time":1785097737}   http_code=200

$ docker exec $C curl -X POST .../api/auth/register -d '{"username":"curltestuser1","password":"curltestpass1"}'
{"token":"fXmJ...","username":"curltestuser1"}   http_code=201

$ docker exec $C curl -X POST .../api/auth/login -d '{"username":"curltestuser1","password":"curltestpass1"}'
{"token":"GaFl...","username":"curltestuser1"}   http_code=200

$ docker exec $C curl -X POST .../api/file/upload -F "file=@/tmp/testflag.txt;filename=f.txt" \
    -F 'json={"token":"GaFl...","visibility":"private"};type=application/json'
{"error":"Token, name, and file content are required"}   http_code=400   # <- reproduksi bug brief

$ docker exec $C curl ... -F 'json={"token":"GaFl...","visibility":"Private"};type=application/json'
{"file_id":5351753945584915633}   http_code=201                          # <- koreksi terbukti

$ docker exec $C curl -X POST .../api/file/download/5351753945584915633 -d '{"token":"GaFl..."}'
content-type: application/octet-stream
content-disposition: attachment; filename="f.txt"
TESTFLAGCURLROUNDTRIP789   http_code=200                                  # <- byte-exact round-trip

$ docker exec $C curl -X POST .../api/file/download/1 -d '{"token":"GaFl..."}'
{"error":"File not found"}   http_code=404                                # <- basis kasus "bogus"
```

### Deploy checker
```
~/adlab/forcad/checkers/_lib/adlab_eno.py                (sudah ada, TIDAK diubah)
~/adlab/forcad/checkers/eno10_flagdrive/checker.py        (baru, mode 755, owner reky:reky)
```
Diff vs repo lokal sebelum gate final: `diff_exit=0` (identik). Sanity-import di dalam
container (`python3 -c "import checker"` dgn sys.path diarahkan manual): sukses, tanpa error.

### Gate run (persis versi checker.py yang di-commit)
```
$ C=$(docker ps -qf name=forcad-celery); IP=192.168.0.17
$ FLAG="ENOTESTFLAGflagdrive9284736501AAAA="

$ docker exec $C /checkers/eno10_flagdrive/checker.py check $IP; echo "check_exit=$?"
check_exit=101

$ docker exec $C /checkers/eno10_flagdrive/checker.py put $IP "" "$FLAG" 0 > /tmp/fd_put.out 2>/tmp/fd_put.err
$ echo "put_exit=$?"
put_exit=101
$ cat /tmp/fd_put.out
{"t":"x8iw9OwHMhOKg2LY5XmOeYiPHilNfhzhpA7QCnCHBgaIKYa69k1SIlRFpdGwn9YHn5vr7R170rgPlLBFWX2d1cIW9CVwfCNFJJbHd2uLB4DpKSZCqIggJ3eQj2P5oMGT","f":"6065122092086717149"}

$ FID=$(cat /tmp/fd_put.out)
$ docker exec $C /checkers/eno10_flagdrive/checker.py get $IP "$FID" "$FLAG" 0; echo "get_exit=$?"
get_exit=101

$ BOGUS='{"t":"x8iw9OwHMhOKg2LY5XmOeYiPHilNfhzhpA7QCnCHBgaIKYa69k1SIlRFpdGwn9YHn5vr7R170rgPlLBFWX2d1cIW9CVwfCNFJJbHd2uLB4DpKSZCqIggJ3eQj2P5oMGT","f":"1"}'
$ docker exec $C /checkers/eno10_flagdrive/checker.py get $IP "$BOGUS" "$FLAG" 0 >/tmp/fd_corrupt.out 2>/tmp/fd_corrupt.err
$ echo "corrupt_exit=$?"
corrupt_exit=102
$ cat /tmp/fd_corrupt.err
[__main__.Checker.get:52] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec $C /checkers/eno10_flagdrive/checker.py check 10.13.37.99 >/tmp/fd_down.out 2>/tmp/fd_down.err
$ echo "down_exit=$?"
down_exit=104
$ cat /tmp/fd_down.err
ConnectionError(MaxRetryError("HTTPConnectionPool(host='10.13.37.99', port=4859): Max retries
exceeded with url: /api/health (Caused by NewConnectionError('...Failed to establish a new
connection: [Errno 113] No route to host'))"))
```

Semua exit code sesuai yang diminta: **101 / 101 / 101 / 102 / 104**.

Catatan mekanisme "bogus flag_id" (sama seperti Task 2/3): bogus HARUS berupa JSON *valid*
dengan isi salah (di sini: token asli + `file_id="1"` yang nonexistent, dikonfirmasi 404 lewat
curl manual di atas), BUKAN string bukan-JSON — kalau bukan-JSON, `A.decode_state` melempar
`ValueError` yang lolos ke `except Exception as e: cquit(A.status_for(e), ...)` di `__main__`,
dan `status_for` memetakan `ValueError` → `MUMBLE` (103), BUKAN `CORRUPT` (102) yang diminta.

### Teardown (setelah gate lolos)
```
$ cd ~/adlab/eno10/flagdrive && docker compose down -v
 Container flagdrive-flagdrive-service-1 Removed
 Container flagdrive-flagdrive-db-1 Removed
 Volume flagdrive_database Removed
 Volume flagdrive_postgres-data Removed
 Network flagdrive_default Removed
teardown_exit=0

$ docker ps -a --format "{{.Names}}" | grep -i flagdrive || echo "no flagdrive containers"
no flagdrive containers

$ docker network inspect forcad_default --format "{{range .Containers}}{{.Name}} {{end}}"
forcad-client-api-1 forcad-ticker-1 forcad-admin-api-1 forcad-events-1 forcad-redis-1
adlab-dashboard adlab-redis forcad-flower-1 forcad-postgres-1 adlab-eno-mongo forcad-celery-1
adlab-eno-shetcode forcad-http-receiver-1 forcad-rabbitmq-1 forcad-nginx-1
```
(15 anggota — sama dgn baseline. Memory available: `6.2Gi` (baseline sblm task) → `6.3Gi`
(sesudah teardown) — stabil, tidak ada resource bocor.)

---

## File yang diubah/dibuat

- **`checkers/enowars10/flagdrive/checker.py`** (baru, executable, 72 baris) — satu-satunya file
  yang di-commit, sesuai instruksi override task.
- **TIDAK diubah**: `deploy/enowars10-deploy.sh`, `forcad/config.enowars10.yml` (registrasi
  ditunda, sesuai instruksi eksplisit), `checkers/enowars10/_lib/*` (di-reuse apa adanya),
  `checkers/requirements.txt` server (tidak perlu dep baru — checker hanya pakai stdlib
  `io`/`json` + `checklib`/`requests`/`adlab_eno` yg sudah ada).

Sisi server (tidak dicommit, konsisten dgn pola checker lain):
- `~/adlab/forcad/checkers/eno10_flagdrive/checker.py` (dibiarkan terpasang di celery).
- `~/adlab/eno10/flagdrive/` — rsync source + `docker-compose.override.yml` tulisan tangan +
  **2 patch dipertahankan** (`Dockerfile` tanpa `--mount=type=cache`, `frontend/index.html` href
  tailwind dikoreksi) — dipertahankan (TIDAK dihapus) utk rebuild berikutnya kalau masuk tahap
  roster; hanya CONTAINER-nya yang di-teardown.
- Laptop source (`~/workspaces/cylab/ctf/.../flagdrive/`) — **tidak disentuh sama sekali**,
  dicek tidak ada operasi write ke path tsb setelah rsync awal.

---

## Self-review

- **Faithfulness ke brief**: struktur `Checker(BaseChecker)`, method `check/put/get`, exception
  handling `__main__` (Checker construction DI LUAR try) dipakai verbatim. Rute, nama field
  multipart (`file`/`json`), bentuk respons login/register, dan nama field `file_id` SEMUA
  benar sesuai brief (dikonfirmasi baca source + curl) — deviasi HANYA pada 1 nilai kritis
  (`visibility` kapital) + 1 perbaikan robustness (byte vs teks di download). Keduanya
  dikonfirmasi empiris via curl manual SEBELUM ditulis ke checker resmi, bukan tebakan.
- **Tidak ada state palsu**: setiap exit code & output di atas hasil run asli berurutan dlm satu
  sesi; token/file_id di evidence gate BERBEDA dari token/file_id di verifikasi manual curl
  (buktinya checker resmi benar-benar dieksekusi ulang dgn kredensial baru, bukan reuse data
  curl manual sebelumnya).
- **Isolasi perubahan**: 2 patch build (Dockerfile cache-mount, index.html href) HANYA di salinan
  server (`~/adlab/eno10/flagdrive/`); laptop source (bank-soal repo terpisah) tidak tersentuh,
  dicek tidak ada operasi write ke path tsb setelah rsync awal.
- **Commit bersih**: `git add` eksplisit 1 file, `git status --porcelain` dicek sebelum & sesudah
  commit — hanya `checkers/enowars10/flagdrive/checker.py` ter-stage (`.omc/` punya orkestrator,
  sudah ada sejak awal sesi, tidak ikut).
- **Resource server**: `flagdrive` di-teardown penuh (`docker compose down -v`), network
  attachment hilang, memory available server balik ke/di atas baseline, tidak ada
  container/volume nyisa.

## Kekhawatiran (bukan blocker)

- Sama seperti catatan Task 3: `assert_eq(r.status_code, 200, ..., Status.CORRUPT)` di `get()`
  menyamaratakan SEMUA non-200 (401 token invalid, 403 access denied, 404 not found, 500 gagal
  dekripsi) jadi CORRUPT — 5xx transien secara prinsip lebih tepat MUMBLE. Preseden identik di
  greple/d3pl0y, sengaja dibiarkan konsisten (kalau mau diperbaiki, sebaiknya sekaligus di
  ketiganya, bukan hanya flagdrive).
- Reaper 12 menit (sama dgn d3pl0y) — relevan utk keputusan `round_time`/`flag_lifetime` di
  `config.enowars10.yml` nanti (belum jadi masalah sekarang krn config ditunda & checker
  registrasi user baru tiap PUT).
- `rand_username()` (adjective+noun+4-digit, ~504,000 kombinasi) bisa kolisi teoretis antar PUT
  (username `PRIMARY KEY`) — kalau kolisi, register balas 409, assert `//100==2` MUMBLE dgn
  benar (bukan crash). Presisi sama dgn risiko yang sudah diterima di greple/d3pl0y, tidak
  diubah.
- Dua patch build server (Dockerfile + index.html) hidup HANYA di `~/adlab/eno10/flagdrive/` —
  kalau server itu di-rebuild dari rsync ulang tanpa membawa 2 patch ini, build akan gagal lagi
  dgn error yang sama. Didokumentasikan penuh di atas supaya reproducible.
