# Task 7 Report: Checker `funsplash` (:1337) — foto/koleksi, body ≤1000 B

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(flag_id bogus, kredensial nyata)=102`,
`check(host mati)=104`. Diulang sekali lagi (put+get round kedua, independen) untuk memastikan
bukan kebetulan — juga 101/101.

Commit: (lihat pesan balik ke pemanggil) — `feat(eno10): checker funsplash (foto/koleksi) + gate
lolos` (branch `enowars10-checkers`), HANYA `checkers/enowars10/funsplash/checker.py`.

Servis Gleam (BEAM) + Postgres 18 ini **butuh 1 patch build di salinan server** (dependency git
`bravo` tak bisa dijangkau — lihat bawah), dan checker-nya **butuh 1 workaround runtime** yang
tak terduga dari statik source manapun: cookie sesi servis ini SELALU ber-flag `Secure` kecuali
diakses via literal `localhost`/`127.0.0.1`, sehingga `requests.Session` polos (http://) menolak
mengirimkannya balik — persis skenario false-negative yang diperingatkan brief soal `/napi/me`,
tapi akar masalahnya lebih dalam dari sekadar "assert login".

---

## Ringkasan alur

1. Baca brief + baca penuh source asli (`router.gleam`, `web/auth.gleam`, `web/collection.gleam`,
   `web/photo.gleam`, `web.gleam`, `server.gleam`, `models/collection.gleam`,
   `shared/shared_login.gleam`, `shared/shared_signup.gleam`, `shared/shared_collection.gleam`,
   `shared/shared_user.gleam`, `init.sql`, `docker-compose.yml`, `gleam.toml`/`manifest.toml`
   ketiga package) sebelum menulis checker — brief eksplisit menghedge route/field dgn "atau".
2. Tulis `checkers/enowars10/funsplash/checker.py` — pola `collections` dipilih (bukan
   `upload`/`photos`), karena `collections.create()` tak butuh data biner/pipeline
   censor/compression sama sekali (lihat §"Kenapa koleksi, bukan foto").
3. rsync `funsplash/` laptop → server (`~/adlab/eno10/funsplash/`, via `--rsync-path=/usr/bin/rsync`
   krn shell non-interaktif server ber-PATH kosong, dan `rsync` lokal tak ketemu di remote tanpa
   itu).
4. Build pertama **gagal**: dependency git `bravo` (`server/gleam.toml`) tak bisa di-clone —
   `github.com` (bukan `codeload.github.com`/`raw.githubusercontent.com`) tak terjangkau dari
   sandbox build. Dipatch (lihat §"Patch build" di bawah): vendor commit yg SUDAH terkunci di
   manifest.toml via tarball `codeload.github.com`, jadikan path-dependency lokal.
5. Build kedua **sukses** (`docker compose build`, ~1 menit stlh fix, tanpa BuildKit issue —
   Dockerfile funsplash TIDAK punya `RUN --mount=type=cache` sama sekali, dicek eksplisit).
6. `docker compose up -d` (postgres18 sehat, cleanup, funsplash) — funsplash publish
   `1337:1337` (internal == eksternal), jadi dipilih pola Task 2-5: connect container ke
   `forcad_default`, gate via IP container (`192.168.0.17:1337`), BUKAN VM tim (kontras Task 6
   yang nginx-fronted 5432≠80).
7. Verifikasi manual bentuk request via `curl` langsung ke `localhost:1337` di server — join,
   login, create-collection, get-collection anonim — SEMUA dikonfirmasi sebelum checker resmi.
   Di sinilah ditemukan: request/respons semuanya form-urlencoded + redirect 303 (bukan
   JSON+"id" spt draft brief), field id publik adalah `public_id`.
8. Tulis ulang checker sesuai temuan #7, deploy ke `forcad-celery-1:/checkers/eno10_funsplash/`
   (mode 755, owner 1000:1000, dicek `nobody` bisa baca+eksekusi).
9. Gate resmi via `docker exec forcad-celery-1 …` — **put() gagal (103) di percobaan pertama**:
   `JSONDecodeError` dari `/napi/me`. Didebug dgn 3 skrip Python iteratif (di-`docker cp` ke
   container yg sama, vantage point identik gate) — ternyata bukan soal request FORM tapi soal
   **cookie sesi ber-flag `Secure` yang tak pernah terkirim balik lewat http:// ke IP container**
   (lihat §"Temuan kritis" — ini SELALU terjadi di jalur nyata manapun, bukan artefak jaringan
   bridge lokal). Ditambahkan `_sync_cookie_header()`, checker ditulis ulang, di-deploy ulang.
10. Gate resmi diulang — **5/5 lolos**. Diulang sekali lagi (put+get round kedua) — konsisten.
11. Teardown (`docker compose down -v` di server), file debug di container dihapus, RAM server
    kembali ke baseline (~6.6Gi available, sama sprt sebelum mulai).
12. Commit HANYA `checkers/enowars10/funsplash/checker.py`. `config.enowars10.yml` TIDAK
    disentuh, TIDAK ada ronde engine dijalankan (sesuai instruksi override task).

---

## Kenapa koleksi, bukan foto

Brief menyebut dua opsi: `/napi/upload` (foto) atau `/napi/collections` (koleksi). Dipilih
**koleksi**, dikonfirmasi via `server/collections.gleam:87-114` (`collections.create`) — insert
`(public_id, name, description, creator, private)` murni, **tanpa keharusan foto sama sekali**
(`photo_public_id` di form opsional, `None` kalau tak dikirim, `collections.get_by_public` juga
tak pernah cek isi foto). `photo.upload()` (`web/photo.gleam:146`, `wisp.require_form` +
multipart) butuh data biner riil lewat pipeline `censor`/`fast_png`/`compression` (lihat
`server/src/png/*.erl`, `*.c`) — jauh lebih rumit dan lebih berisiko menabrak limit body 1000 B
drpd form kecil `name`+`description`. Koleksi memberi round-trip penuh (create → baca balik via
`GET /napi/collections/{public_id}`) tanpa menyentuh subsistem foto sama sekali.

---

## Koreksi menyeluruh terhadap brief (semua dikonfirmasi baca source, LALU diverifikasi live)

Python di brief mengasumsikan body JSON (`json={...}`) dan respons JSON berisi field
`id`/`public_id` langsung. **Keduanya salah** untuk servis ini:

1. **Body form-urlencoded, bukan JSON.** `auth.login()` (`auth.gleam:57`), `auth.sign_up()`
   (`auth.gleam:109`), `collection.create()` (`collection.gleam:96`) semua pakai
   `wisp.require_form(request)` — field dibaca dari `shared_login.form()`/`shared_signup.form()`/
   `shared_collection.collection_create_form()`, yang parse dari
   x-www-form-urlencoded/multipart. Checker pakai `data={...}` (requests set Content-Type
   otomatis).

2. **`sign_up` butuh field wajib `first_name`** yang tak disebut brief sama sekali
   (`shared_signup.gleam:45-48`, `form.check_not_empty` — tanpa field ini form gagal validasi,
   redirect ke `/?error=Invalid form data`, bukan sukses). `last_name`/`bio`/
   `available_for_hire` optional/checkbox — aman diabaikan sepenuhnya (dikonfirmasi baca source
   `formal` v3.0.1 `form.gleam`: `parse_checkbox` atas field yang SAMA SEKALI tak ada di values →
   `[] -> False`, bukan error; `parse_optional` serupa).

3. **Respons join/login/create-collection adalah redirect 303, BUKAN JSON.**
   `auth.gleam:87` (login sukses → `wisp.redirect("/")` + `set_cookies`),
   `auth.gleam:139` (join sukses → `wisp.redirect("/?registered=true")` + `set_cookies` yang SAMA
   — sign_up auto-login), `collection.gleam:131-136` (create sukses → redirect ke
   `"/collections/" <> collection.public_id`, karena checker tak mengirim `redirect_to`).
   Dikonfirmasi live via `curl -i`: semua balas `HTTP/1.1 303 See Other`.
   - Id koleksi diambil dari **header `Location`** (bukan regex/JSON body), dengan
     `allow_redirects=False` supaya tak ikut lompat ke halaman index.
   - Sukses/gagal join & login **tidak bisa** disimpulkan dari status akhir kalau redirect
     diikuti — kedua rute sukses (`/?registered=true`, `/`) maupun rute gagal (`/?error=...`,
     `/login?error=...`) sama-sama jatuh ke fallback GET `_ if request.method == http.Get ->
     serve_index(context)` di `router.gleam:79`, yang **selalu balas 200** (index.html statis).
     Jadi checker membuktikan sukses lewat `GET /napi/me` (lihat poin 5), bukan dari status
     redirect join/login itu sendiri.

4. **Field pengenal publik koleksi adalah `public_id`**, bukan `id` — sesuai alternatif kedua
   yang disebut brief. Dikonfirmasi `models/collection.gleam:11-23`
   (`pub type PublicId = String`, `Collection(... public_id: PublicId ...)`) dan
   `shared/shared_collection.gleam:20-32` (`collection_to_json` memancarkan key `"public_id"`,
   BUKAN `"id"`). Live: `{"public_id":"xq_X09_oKBT","name":"MyColl","user":{...},
   "description":"FLAG{...}","private":false}`.

5. **`GET /napi/collections/{id}` tidak mewajibkan login sama sekali.**
   `web/collection.gleam:69-90` — tak ada `auth.require_login`, tak ada pengecekan field
   `private` apa pun (bug arsitektur servis, dicatat sbg observasi murni — lihat §"Observasi",
   bukan dieksploitasi checker). Dikonfirmasi live: `curl` TANPA cookie ke koleksi yang baru
   dibuat tetap balas 200 + body lengkap termasuk `description`. Ini persis alasan catatan
   tugas menekankan: login di `get()` **wajib** dibuktikan lewat `GET /napi/me`
   (`auth.gleam:40-47`, 200+JSON `{"username":...}` hanya kalau `context.user` `Some`), BUKAN
   diasumsikan dari "request login tak error" — karena kalau login diam-diam gagal, `GET`
   koleksi (yang `private=false`) tetap 200 dengan flag di dalamnya → false-OK kalau assert ini
   dilewati. Kegagalan login diklasifikasikan **MUMBLE** (servis hidup, autentikasi rusak),
   bukan CORRUPT.

Deviation kecil lain: `check()` dipertahankan sama seperti draft brief (`GET /` → 200) karena
`router.gleam` dibaca penuh dan memang **tak ada rute health/info JSON** di servis ini (beda dari
overeats/signmemaybe/flagdrive) — konsisten dengan preseden d3pl0y/greple untuk servis tanpa rute
kesehatan tersendiri.

---

## Temuan kritis: cookie sesi selalu `Secure`, tak pernah "localhost" di jalur nyata

Ini BUKAN sesuatu yang bisa ditemukan dari membaca `router.gleam`/`web/*.gleam` saja — hanya
terlihat lewat pengujian live ke servis via IP (bukan `localhost`), yang justru merupakan **satu-
satunya cara ForcAD benar-benar akan menjangkau servis ini** di round sungguhan.

**Mekanisme** (dikonfirmasi baca source wisp v2.2.2, fungsi `set_cookie` di `wisp.gleam`):

```gleam
let scheme = case request.host {
    "localhost" | "127.0.0.1" | "[::1]" if request.scheme == http.Http ->
      case request.get_header(request, "x-forwarded-proto") {
        Ok(_) -> http.Https
        Error(_) -> http.Http
      }
    _ -> http.Https
  }
```

Cookie (`uid`, `uname`, disetel `auth.gleam:94-104`) ditandai `Secure` **kecuali** request-host
persis `localhost`/`127.0.0.1`/`[::1]` **dan** skema http **dan** tanpa header
`x-forwarded-proto`. ForcAD tidak pernah memanggil checker via literal `"localhost"` (selalu IP
container/VM) → di **setiap** jalur nyata, Set-Cookie servis ini SELALU ber-flag `Secure`.

**Dampak**: `requests.Session` (dipakai `A.http()`, murni `http://`, sesuai keseluruhan model
lalu lintas checker ForcAD yang memang tanpa TLS) taat RFC 6265 §4.1.2.5 — cookie ber-flag
`Secure` tidak pernah dilampirkan balik ke request non-https, **bahkan ke host yang sama persis**
yang menerbitkannya. Dikonfirmasi lewat 3 skrip debug iteratif langsung ke instance live
(`192.168.0.17:1337`, vantage point identik dengan gate resmi):

- Percobaan 1 (mengganti `http.cookiejar.DefaultCookiePolicy(secure_protocols=("http","https"))`
  pada `session.cookies`): **tidak mengubah apa pun** — `GET /napi/me` tetap kembali sbg request
  anonim (200 tapi body index.html, bukan JSON `{"username":...}`), krn redirect
  `allow_redirects=True` bawaan jatuh ke fallback index yg sama disebut poin 3 di atas.
- Percobaan 2 (menyalin nilai cookie dari jar secara manual ke header `Cookie` per-request):
  **terbukti bekerja** — `GET /napi/me` balas 200 + JSON user yang benar.
- Percobaan 3 (menyetel `session.headers["Cookie"]` sekali sbg default, bukan per-call, lalu
  diuji lintas SESI BARU meniru `get()` sungguhan — login ulang dari nol): **konsisten bekerja**.

**Fix yang dipakai** (`_sync_cookie_header(s)` di checker, dipanggil tepat setelah
`POST /napi/join` dan setelah `POST /napi/login`, sebelum request terautentikasi berikutnya):

```python
def _sync_cookie_header(s):
    s.headers["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
```

Ini bukan "melewati keamanan" — checker hanya meneruskan nilai yang server sendiri baru saja
berikan, kembali ke server yang sama, lewat jalur yang sama persis dengan yang dipakai server
untuk menerbitkannya. Tanpa fix ini, `put()`/`get()` akan **selalu** salah mengklasifikasi sesi
sebagai anonim setelah join/login yang sebenarnya berhasil — false-negative permanen di jalur
manapun kecuali checker dijalankan dari `localhost` (yang tak pernah terjadi di produksi ForcAD).

Sempat dicurigai juga `wisp.csrf_known_header_protection` (`web.gleam:20`) sbg biang keladi
(strip header `Cookie` dari request kalau tak ada `Origin`/`Referer` yang cocok Host) — dibaca
source-nya (`raw.githubusercontent.com/gleam-wisp/wisp/v2.2.2/src/wisp.gleam`), TERNYATA tidak
relevan di sini: `context.user` (dipakai semua handler) di-resolve di `server.gleam:29`
(`auth.get_user_from_session`) **sebelum** `web.middleware`/CSRF check pernah berjalan — jadi
stripping cookie oleh middleware itu tak pernah memengaruhi hasil. Dicatat di sini supaya
investigasi ini tak terulang kalau checker lain nanti menunjukkan gejala serupa.

---

## Patch build (SERVER SAJA — laptop `~/workspaces/cylab/ctf/.../funsplash/` TIDAK disentuh)

`server/gleam.toml` mendeklarasikan dependency git:
`bravo = { git="https://github.com/bird-dancer/bravo", ref = "main" }` (binding ETS, dipakai
cache in-memory servis). Build pertama gagal tepat di `gleam deps download` utk package
`server`:

```
error: Shell command failure
There was a problem when running the shell command `git`.
The error from the shell command was:
    fatal: unable to access 'https://github.com/bird-dancer/bravo/': Failed to connect to
    github.com port 443 after 133224 ms: Could not connect to server
```

Dicek lebih lanjut dari server (`curl` dgn timeout 8s):
`github.com` → timeout murni (exit 124); `codeload.github.com` → 301 (OK);
`raw.githubusercontent.com` → 301 (OK); `hex.pm` → 200 (OK, package hex lain semua sukses
duluan: "Downloaded 10 packages"/"Downloaded 44 packages" utk `shared`/`client`). Pola ini persis
seperti block SNI/hostname yg cuma menyasar host utama `github.com`, bukan gangguan GitHub
menyeluruh — dan cocok dgn peringatan brief ttg "mirror workaround" servis ENOWARS sebelumnya.

**Fix**: manifest.toml SUDAH mengunci commit persis (`d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9`
di branch `main`) — jadi tarball di-ambil via `codeload.github.com` (yang terjangkau) pada commit
TERKUNCI itu (bukan `main` HEAD, supaya tak ada risiko drift), diekstrak ke
`~/adlab/eno10/funsplash/vendor/bravo/`, lalu `gleam.toml`/`manifest.toml`/`Dockerfile` dipatch
supaya `bravo` jadi path-dependency lokal alih-alih git-dependency. Diverifikasi `gleam.toml`
bravo (`version = "0.0.0"`, deps `gleam_stdlib`+`gleam_erlang`) SAMA PERSIS dgn yang sudah
terkunci di manifest lama — jadi bukan downgrade/upgrade diam-diam.

```diff
--- Dockerfile (asli)
+++ Dockerfile (server, ~/adlab/eno10/funsplash/Dockerfile)
@@ -13,6 +13,15 @@
 COPY ./server/manifest.toml /build/server/
 COPY ./server/gleam.toml /build/server/

+# adlab patch: bravo is a git dependency (github.com/bird-dancer/bravo) but this
+# build sandbox cannot reach github.com over 443 (codeload.github.com and
+# raw.githubusercontent.com work fine - looks like an SNI/hostname-based block on
+# just the main github.com host, not a blanket GitHub outage). Vendored the exact
+# commit already pinned in manifest.toml (d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9)
+# via codeload tarball into ./vendor/bravo, and repointed gleam.toml/manifest.toml
+# at a local path dependency instead. Copy it in before deps download needs it.
+COPY ./vendor /build/vendor
+
 RUN cd /build/shared && gleam deps download
 RUN cd /build/client && gleam deps download
 RUN cd /build/server && gleam deps download
```

```diff
--- server/gleam.toml (asli)
+++ server/gleam.toml (server)
@@ -26,7 +26,7 @@
 formal = ">= 3.0.1 and < 4.0.0"
 gleam_json = ">= 3.1.0 and < 4.0.0"
 gleam_time = ">= 1.8.0 and < 2.0.0"
-bravo = { git="https://github.com/bird-dancer/bravo", ref = "main" }
+bravo = { path = "../vendor/bravo" }
 mimetype = ">= 0.24.0 and < 1.0.0"
 file_streams = ">= 2.0.0 and < 3.0.0"
```

```diff
--- server/manifest.toml (asli)
+++ server/manifest.toml (server)
@@ -9,7 +9,7 @@
  packages = [
    { name = "argv", ... },
    { name = "backoff", ... },
-  { name = "bravo", version = "0.0.0", build_tools = ["gleam"], requirements = ["gleam_erlang", "gleam_stdlib"], source = "git", repo = "https://github.com/bird-dancer/bravo", commit = "d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9" },
+  { name = "bravo", version = "0.0.0", build_tools = ["gleam"], requirements = ["gleam_erlang", "gleam_stdlib"], source = "local", path = "../vendor/bravo" },
    { name = "directories", ... },
 ...
 [requirements]
-bravo = { git = "https://github.com/bird-dancer/bravo", ref = "main" }
+bravo = { path = "../vendor/bravo" }
  envoy = { version = ">= 1.0.1 and < 2.0.0" }
```

Plus direktori baru `~/adlab/eno10/funsplash/vendor/bravo/` (isi tarball `bird-dancer/bravo` @
`d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9`, tak dicommit — cuma di server, sama seperti pola
patch greple/flagdrive). Build kedua sukses bersih tanpa keluhan BuildKit apa pun (Dockerfile
funsplash memang tak punya blok `RUN --mount=type=cache` sama sekali — dicek eksplisit
`grep -rn "mount=type=cache"` nihil di `Dockerfile`/`server/`/`client/`/`shared/`).

**UTANG TEKNIS** (menambah entri yang sama yang sudah dicatat `progress.md` utk greple/
flagdrive): patch build (Dockerfile+gleam.toml+manifest.toml+vendor/bravo) ini HANYA ada di
`~/adlab/eno10/funsplash/` di server, TIDAK di repo ini. rsync ulang dari laptop akan
menghapusnya lagi (`--delete` dipakai) dan build akan gagal lagi dgn error sama. Ini kejadian
ke-3 pola ini (greple/Zig, flagdrive/BuildKit+href, sekarang funsplash/bravo-vendor) — makin
menguatkan usulan `progress.md` soal task khusus "simpan patch build di repo
(`deploy/patches/<service>.patch`)".

---

## Keputusan infra: forcad_default + IP container (pola Task 2-5, bukan Task 6)

`docker-compose.yml` funsplash: `ports: ["1337:1337"]`, `.env`: `SERVER_PORT=1337`. Internal
listen port == published port (dikonfirmasi log container: `Listening on http://0.0.0.0:1337`)
→ pola Task 2-5 berlaku apa adanya (BUKAN kasus nginx-fronted Task 6 di mana port publish ≠ port
internal). `docker network connect forcad_default funsplash_service-funsplash-1` →
IP `192.168.0.17`. Gate: `docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py
<action> 192.168.0.17 ...`.

---

## Gate — lima kasus wajib

```
$ docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py check 192.168.0.17
check_exit=101

$ FLAG='ENOTESTFLAGfunsplash19283746XYZa='
$ docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py put 192.168.0.17 "" "$FLAG" 0
put_exit=101
stdout: {"u":"FairQuartz7147","p":"TidmX6gz9A9nI2j5","cid":"TK5i12NsLnp"}

$ FID='{"u":"FairQuartz7147","p":"TidmX6gz9A9nI2j5","cid":"TK5i12NsLnp"}'
$ docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py get 192.168.0.17 "$FID" "$FLAG" 0
get_exit=101

$ BOGUS='{"u":"FairQuartz7147","p":"TidmX6gz9A9nI2j5","cid":"zzznonexist1"}'   # kredensial NYATA, cid tak ada
$ docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py get 192.168.0.17 "$BOGUS" "$FLAG" 0
get_bogus_exit=102
stderr: [__main__.Checker.get:153] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec forcad-celery-1 /checkers/eno10_funsplash/checker.py check 10.13.37.99
check_down_exit=104
stderr: ConnectionError(... Failed to establish a new connection ... No route to host)
```

Ringkasan: **check=101, put=101, get=101, get(bogus, kredensial nyata)=102, check(host mati)=104**
— semua sesuai permintaan. Diulang sekali lagi (put/get round kedua, flag & user berbeda) —
101/101 konsisten, memastikan fix cookie bukan kebetulan satu kali jalan.

---

## checker_timeout yang disarankan

`put()` = 3 request berurutan (join, `/napi/me`, create-collection); `get()` = 3 request
berurutan (login, `/napi/me`, get-collection). Semua respons di server host terasa hampir
instan (BEAM/Gleam, connection pool Postgres 100). Disarankan **`checker_timeout: 15`** —
cukup markup di atas kondisi normal (tiap request pakai timeout internal harness 10s, tapi 3
request berurutan bisa saja butuh retry TCP kalau jaringan vulnbox sedikit lambat saat round
sungguhan) tanpa berlebihan seperti servis lain yang jauh lebih banyak round-trip (mis. overeats
7 round-trip → 30).

---

## Yang TIDAK diverifikasi / di luar cakupan

- Registrasi `config.enowars10.yml` dan verifikasi `UP` di engine — sengaja di-skip sesuai
  resolusi ambiguitas dari pemberi tugas (Step 4 brief ditunda).
- Jalur `photo.upload()`/`/napi/photos/{id}` sama sekali tak disentuh checker (dipilih koleksi,
  lihat §"Kenapa koleksi, bukan foto") — kalau nanti ternyata ada motif tambahan utk memakai foto
  (mis. utk cakupan attack-surface checker yang lebih luas), itu di luar cakupan task ini.
  `available_for_hire`/`last_name`/`bio` (signup), `private=true`/`photo_public_id`/`redirect_to`
  (create-collection) tak pernah dites krn memang tak dipakai checker.
  `update`/`delete`/`add_photo`/`remove_photo`/`like`/`account` juga tak disentuh (tak perlu utk
  round-trip put/get).
- Perilaku di bawah beban/konkurensi (banyak round paralel) tak diuji — hanya path tunggal
  sekuensial per aksi, sesuai model checker ForcAD (satu proses per aksi per target).
  `cleanup.sh` (hapus baris >11 menit) tak diuji bentrok dgn `checker_timeout`/`flag_lifetime`
  round sungguhan — perlu diperhitungkan saat config disusun nanti (mirip catatan Task 3 soal TTL
  d3pl0y).
- Kenapa `set_policy(secure_protocols=...)` tak berhasil (padahal API publik stdlib) tak digali
  sampai akar penyebab pastinya di internal `requests`/`http.cookiejar` — cukup dibuktikan tak
  bekerja empiris lalu dipakai fix alternatif yang TERBUKTI bekerja (`_sync_cookie_header`).

---

## Observasi arsitektur (bukan tindakan checker, murni catatan)

- `web/collection.gleam:69-90` (`collection.get`) tidak pernah memeriksa field `private` — koleksi
  privat pun bisa dibaca siapa pun yang tahu `public_id`-nya (tak perlu login/kepemilikan). Bisa
  jadi memang bagian dari permukaan kerentanan yang dimaksud game ini; dicatat murni sbg observasi,
  sama seperti catatan password plaintext di overeats (Task 6)/Rust service (Task 4).
- `public_id` (koleksi/foto/user) di-generate `id_server.gleam` — 9 byte random via `rand:bytes`
  di-base64url-encode lalu di-slice 11 karakter (buang 1 karakter pertama) — 66 bit entropi,
  bukan celah praktis, dicatat sekadar utk konteks kenapa regex brief (`[A-Za-z0-9_-]+`) memang
  cocok formatnya (walau akhirnya dipakai parsing `Location`/JSON, bukan regex).

## Concerns

1. **Cookie-Secure workaround** (`_sync_cookie_header`) adalah bagian paling tidak biasa dari
   checker ini — kalau wisp/servis berubah perilaku cookie-nya di masa depan (mis. mulai
   menghormati `X-Forwarded-Proto` dari proxy sungguhan), fix ini tetap aman (no-op harmless: cuma
   menyalin nilai cookie yang memang sudah ada di jar), tapi kalau servis BERHENTI menandai
   `Secure` sama sekali, fix ini juga tetap aman — jadi tak perlu revisit kecuali gate mulai gagal.
2. Utang teknis patch build server-only bertambah lagi (3 servis sekarang: greple, flagdrive,
   funsplash) — mendukung usulan `progress.md` soal task dedicated menyimpan patch di repo.
3. `first_name` acak dipakai `A.rand_username()` (bukan `A.rand_text()`) supaya dijamin non-kosong
   by construction — konsisten dgn field `name`/`username`/`password` lain di checker ini, semua
   dari generator harness yang sama (tak ada dependency baru).

---

## Fix round 1 (review Task 7 — 1 Important)

**Temuan**: `checker.py:116` dan `:148` — `s.get("/napi/me")` tak punya `allow_redirects=False`,
beda dari tiap request lain di file ini (`:111`, `:123`, `:140`). Kalau sesi anonim, `/napi/me`
303-redirect ke `/?error=...`; tanpa `allow_redirects=False`, `requests` ikut redirect itu dan
jatuh ke fallback GET index (`router.gleam` catch-all, selalu 200) — jadi
`assert_eq(me.status_code, 200, ...)` **selalu lolos**, apa pun status login sebenarnya. Sinyal
gagal yang asli baru muncul 1 baris kemudian sbg `JSONDecodeError` mentah dari `me.json()`,
tertangkap generik oleh `except Exception` di `__main__` dan tetap terklasifikasi MUMBLE lewat
`status_for` — tapi pesan diagnostik yang sengaja ditulis ("join/login gagal (sesi tak valid)")
tak pernah terpakai, diganti `repr(JSONDecodeError(...))` yang kriptis. Persis kejadian yang
dialami saat development sblm `_sync_cookie_header` ditambahkan (lihat gate pertama task ini:
103 + `JSONDecodeError`), yang masih jadi fallback diam-diam kalau workaround cookie itu nanti
regresi sebagian.

**Fix** (scope ketat, HANYA 2 baris, tak ada lagi yg disentuh — commit `af74796`):

```diff
-        me = s.get("/napi/me")
+        me = s.get("/napi/me", allow_redirects=False)
         self.assert_eq(me.status_code, 200, "join gagal (sesi tak valid)", Status.MUMBLE)
```
(muncul 2×: `put()` dan `get()`, pesan assert masing2 tetap "join gagal.../"login gagal...").

**Pembuktian titik perbaikan** (diminta reviewer, dilakukan via 2 salinan scratch di
`/checkers/.scratch_fix1/` pada `forcad-celery-1` — BUKAN file resmi, dihapus lagi stlh dipakai
— `_sync_cookie_header(s)` dimatikan di `put()` utk mensimulasikan regresi cookie-workaround):

- **Sesudah fix** (`allow_redirects=False` ada, cookie-sync dimatikan) —
  `put` → **exit 103**, stdout **`join gagal (sesi tak valid)`** (pesan yg memang dimaksud),
  stderr `equality assertion failed: 303 (<class 'int'>) != 200 (<class 'int'>)` — bersih & tepat
  sasaran.
- **Sebelum fix** (tanpa `allow_redirects=False`, cookie-sync dimatikan, mereproduksi bug asli) —
  `put` → exit 103 juga, TAPI stdout cuma `checker error`, stderr
  `JSONDecodeError('Expecting value: line 1 column 1 (char 0)')` — persis gejala yang
  dilaporkan reviewer.

Status akhir (103/MUMBLE) sama di kedua kasus — persis seperti dicatat reviewer ("tidak
membalik outcome Status hari ini") — tapi kualitas diagnostiknya jauh berbeda, dan itulah yang
diperbaiki.

**Re-gate penuh stlh fix** (service dibawa naik lagi dari image yang SUDAH ter-cache
`funsplash_service-funsplash:latest` — TIDAK perlu rebuild Gleam sama sekali, patch build server
di `~/adlab/eno10/funsplash` masih utuh; IP `forcad_default` yang didapat sama,
`192.168.0.17:1337`):

```
check                                    → 101
put                                      → 101  (flag_id: {"u":"AbleCedar8032","p":"3FPXVvXzBBeL12j5","cid":"j8uavFD5Loe"})
get (flag_id nyata di atas)              → 101
get (state well-formed, cid tak ada)     → 102  ("koleksi tak terambil", 404 != 200)
check (host mati, 10.13.37.99)           → 104  (No route to host)
```

Tak ada regresi. Service di-teardown lagi (`docker compose down -v`) stlh gate, RAM server
kembali ke baseline (~6.6Gi available). `md5sum` checker terdeploy vs repo lokal dicek identik
sblm gate.
