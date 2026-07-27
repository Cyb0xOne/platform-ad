# Task 8 Report: Checker `leet-date` (:6789) — profil bio, cookie session

## Status: DONE

Checker ditulis, di-deploy ke `forcad-celery-1:/checkers/eno10_leet_date/checker.py`, dan
digate penuh terhadap instance live leet-date (stack 6 container: db, payments, imgsvc,
leetdate, cleanup, web) yang dijalankan di VM tim `10.13.37.12`. Kelima kasus gate wajib LOLOS
tepat sesuai kontrak (101/101/101/102/104), plus satu ronde put/get kedua yang independen
(101/101) untuk memastikan bukan kebetulan. Tidak ada patch build server yang diperlukan sama
sekali — ini kejadian pertama di antara 8 task sejauh ini.

BASE commit: `af74796` (funsplash fix round 1).

## Ringkasan alur

1. Baca brief, baca seluruh source Go relevan (`router.go`, `auth.go`, `profiles.go`,
   `health.go`, `sessions.go`, `config.go`) + `docker-compose.yml` + `web/nginx.conf` +
   `web/src/api.ts` (TypeScript client, dipakai sebagai konfirmasi independen kedua atas bentuk
   request/respons, bukan sekadar baca handler Go saja).
2. rsync source laptop → server (`~/adlab/eno10/leet-date/`) → VM tim `10.13.37.12`
   (`~/adlab/eno10/leet-date/`), dua hop persis pola Task 6. `rsync` lokal butuh
   `--rsync-path=/usr/bin/rsync` eksplisit di kedua hop karena shell non-interaktif remote
   ber-PATH kosong (gotcha infra yang sudah didokumentasikan) — tanpa itu rsync gagal
   "command not found: rsync" di sisi remote.
3. `docker compose build` di VM — **sukses bersih tanpa modifikasi apa pun** pada kedua
   Dockerfile yang punya `RUN --mount=type=cache,...` (Dockerfile utama + Dockerfile.imgsvc).
   Dicek eksplisit: VM `10.13.37.12` punya `docker buildx` dengan builder `default` **status
   "running"**, BuildKit v0.31.2 aktif — beda dari server utama (`192.168.43.136`) yang menurut
   brief tak punya BuildKit. Detail di §"Build".
4. `docker compose up -d` — 6 kontainer up, `web` publish `0.0.0.0:6789->8080/tcp` di VM (dicek
   `ss -tln`).
5. **Verifikasi manual live** (Python `requests` dari dalam `forcad-celery-1`, target IP VM
   langsung — bukan asumsi/tebakan) sebelum menulis checker final: register tanpa
   `display_name` → 400 (mengonfirmasi field wajib yang tak disebut brief); register lengkap →
   201 + `Set-Cookie` TANPA flag `Secure`; `GET /api/me` langsung 200 tepat setelah register
   TANPA panggilan `/api/login` terpisah (auto-login terbukti); `PATCH /api/me` dengan
   `{"bio": flag}` → 200, field `bio` di respons berisi flag persis; `GET /api/users/{handle}`
   dari sesi Python **baru** (tanpa cookie sama sekali) → 200 + bio lengkap; `GET
   /api/users/{handle-tak-ada}` anonim → 404. Semua 6 titik ini match 100% dengan pembacaan
   source di langkah 1 — checker final ditulis berdasarkan kombinasi keduanya.
6. Tulis `checkers/enowars10/leet-date/checker.py`, deploy ke celery (`docker cp`, permission
   dicek eksplisit sbg user `nobody`), gate 5 kasus + 1 ronde ekstra (lihat §Gate).
7. Teardown (`docker compose down -v` di VM) + bersihkan file scratch di server/celery.
8. Config (`config.enowars10.yml`) **TIDAK disentuh** dan **TIDAK ada engine round** — sesuai
   resolusi eksplisit ambiguitas brief Step 4 (ditunda).

## Koreksi menyeluruh terhadap brief (semua dikonfirmasi baca source, LALU diverifikasi live)

1. **Topologi 6-container: `PORT` checker (6789) adalah host-publish murni, bukan port
   internal.** `docker-compose.yml:98-107` — service `web` (nginx) `ports: ["6789:8080"]`.
   Container app Go (`leetdate`) sendiri **tidak punya published port ke host sama sekali**,
   hanya `LISTEN_ADDR: ":8000"` di jaringan compose privat dengan IP tetap `172.28.0.10`
   (`docker-compose.yml:52-74`). `web/nginx.conf:16-28` reverse-proxy `location /api/` →
   `leetdate_up` (`172.28.0.10:8000`). Ini **persis** pola "host publish ke port internal
   berbeda" yang diperingatkan brief untuk kasus Task 6 (overeats): attach-ke-`forcad_default`
   + gate-IP-container **tidak bisa** dipakai di sini karena tak ada container yang benar-benar
   `LISTEN` di `:6789`. **Keputusan: dijalankan di VM tim (`10.13.37.12`), digate ke IP VM itu.**

2. **`POST /api/register` wajib field `display_name`** — `auth.go:27` (`registerReq.DisplayName`),
   divalidasi panjang 1-64 di `auth.go:55-58` (`c.JSON(400, {"error":"display_name must be
   1-64 chars"})`). Draf brief cuma kirim `handle`+`password`; dikonfirmasi live (lihat langkah
   5 di atas) balas 400 tanpa field ini. Fix: `put()` mengirim `dn = A.rand_username()` sebagai
   `display_name` — tak butuh dependency baru, generator harness yang sama dipakai ulang untuk
   field ketiga (konsisten dengan pola funsplash `first_name` di Task 7).
   `handle` sendiri di-lowercase SEBELUM divalidasi regex `^[a-z0-9_]{3,20}$`
   (`auth.go:48,51`), jadi `A.rand_username()` (mengandung huruf kapital, mis. `"EagerComet4061"`)
   aman dipakai apa adanya — server yang menormalkan.

3. **Register SUDAH auto-login — panggilan `POST /api/login` terpisah di draf brief adalah
   REDUNDAN, dan dihapus dari `put()`.** `auth.go:85-90` (Register) memanggil
   `auth.CreateSession` + `auth.SetSessionCookie` **tepat sama** seperti `auth.go:126-131`
   (Login). Dikonfirmasi live: `GET /api/me` balas 200 langsung setelah `register`, tanpa
   `login` sama sekali. Bukti tak-langsung tapi tegas ada di checker sendiri: `PATCH /api/me`
   berada di belakang middleware `auth.RequireAuth` (`router.go:53-54`, cuma di-`Use` pada
   subgroup `authed`) yang membalas 401 kalau cookie tak valid — jadi `assert_eq(status, 200,
   ..., MUMBLE)` pada respons PATCH **sekaligus** jadi bukti sesi register benar-benar valid,
   bukan diasumsikan dari status sukses register semata (persis semangat instruksi soal
   "assert login berhasil sbg MUMBLE" walau di sini buktinya lewat efek-samping PATCH, bukan
   endpoint `/me` terpisah, karena `register` sendiri sudah mengembalikan body — beda dari
   funsplash yang responsnya cuma redirect kosong).

4. **Field bio dikonfirmasi**: `PATCH /api/me`, body JSON `{"bio": <flag>}` (`profiles.go:57-65`
   `patchReq.Bio *string`; `profiles.go:214-222` — disimpan **apa adanya** via `nullIfEmpty`,
   **tanpa** `strings.TrimSpace` yang dipakai field lain seperti `city`/`gender`). Respons PATCH
   sukses (200) **bukan echo body request** — `PatchMe` memanggil `d.Me(c)` di baris akhir
   (`profiles.go:274`) yang **re-SELECT penuh dari Postgres** (`profiles.go:74-87`), jadi field
   `bio` pada respons PATCH sendiri sudah genuine round-trip lewat DB sejak `put()`, dikonfirmasi
   live (`bio` di respons PATCH = flag persis).

5. **`GET /api/users/{handle}` adalah rute PUBLIK — `get()` tidak perlu login sama sekali.**
   `profiles.go:103-138` (`PublicProfile`) terdaftar di grup `api` luar (`router.go:50`), BUKAN
   di grup `authed` (`router.go:53-75`, perhatikan `auth.RequireAuth` cuma di-`Use` pada
   subgroup ini). Dikonfirmasi live pakai sesi Python **baru sama sekali** (tanpa cookie apa
   pun) tetap balas 200 + bio lengkap; juga konsisten dengan `web/src/api.ts:150-151`
   (`getUser` dipanggil independen dari status sesi). State karenanya **cukup simpan handle**
   (`A.encode_state(h=handle)`), tak perlu password — resolusi eksplisit brief soal "simpan apa
   yang benar-benar dibutuhkan `get()`". Handle tak ditemukan **atau** format tak valid
   (`profiles.go:105-108`, dua-duanya lewat `handleRe.MatchString` yang sama) **sama-sama**
   balas 404 `{"error":"user not found"}` — dikonfirmasi live — cocok pas dengan kontrak gate
   "GET flag_id palsu (JSON valid, handle tak ada) → CORRUPT".

6. **`check()` pakai `GET /api/healthz`, bukan `/`** — `health.go:9-11` (`{"ok":true}`, 200),
   diproksi `nginx.conf:16` (`location /api/`) ke backend Go. Ini pemeriksaan liveness aplikasi
   asli (Gin + koneksi pool Postgres tersirat oleh proses hidup), bukan cuma `index.html` statis
   nginx seperti `/` yang dipakai draf brief/preseden funsplash — funsplash memang **tak
   punya** rute health JSON tersendiri (dicek waktu itu), leet-date **punya**, jadi dipakai.

## Jebakan #1 (cookie Secure) — TIDAK berlaku di deployment ini, dibuktikan bukan diasumsikan

Cookie sesi `ld_session` (`sessions.go:17`) diset lewat `SetSessionCookie` (`sessions.go:79-82`):
`SameSite=Lax`, `HttpOnly=true`, `Secure=cfg.CookieSecure`. `cfg.CookieSecure` dibaca di
`config.go:26` sebagai `os.Getenv("COOKIE_SECURE") == "1"`, dan `docker-compose.yml:56` set
literal `COOKIE_SECURE: "0"` — jadi `Secure` **selalu false untuk deployment ini**, tidak
bergantung sama sekali pada hostname/skema request (beda dari kasus Task 7: wisp/Gleam yang
Secure-nya bergantung pada apakah host request persis `"localhost"`).

Dibuktikan live, bukan diasumsikan dari baca `config.go` saja:
```
Set-Cookie: ld_session=8add90b8...; Path=/; Max-Age=86399; HttpOnly; SameSite=Lax
```
— tidak ada token `Secure` di header ini sama sekali. `requests.Session` bawaan (`A.http()`,
`http://` murni) berhasil mengirim balik cookie ini ke `PATCH /api/me` tanpa perlakuan khusus
apa pun (tidak perlu `_sync_cookie_header` ala funsplash). Checker ini **tidak** memerlukan
workaround cookie manual.

## Jebakan #2 (redirect membuat assert berbohong) — dimitigasi proaktif

Semua request yang di-assert statusnya (`register`, `patch`, `get users/{handle}`) memakai
`allow_redirects=False` eksplisit, walau pengecekan struktural router Gin tidak menunjukkan
risiko redirect nyata untuk rute-rute exact-match ini (tak ada ambiguitas trailing-slash antara
path yang diminta vs yang terdaftar). Dipasang sebagai pertahanan berlapis mengikuti pelajaran
Task 7, bukan karena ditemukan redirect aktual di sini.

## Keputusan infra: VM tim, bukan `forcad_default`

Lokasi servis: VM tim `reky@10.13.37.12`, `~/adlab/eno10/leet-date/`, docker compose plain
(bukan lewat `deploy/enowars10-deploy.sh` — skrip itu untuk pola attach-`forcad_default`, tak
relevan untuk pola VM). Checker digate lewat `docker exec` dari `forcad-celery-1`, target IP
`10.13.37.12`, port `6789` (host-published asli di VM).

Alasan pemilihan `.12` atas `.11`: keduanya diperiksa dulu (RAM ~2.1Gi available, disk 11-12GB
free, tak ada yang listen `:6789`/`:8080` di keduanya) — dipilih `.12` semata untuk menyebar
beban dari overeats (Task 6) yang meninggalkan source (tanpa container jalan) di `.11`,
menghindari kebingungan direktori, bukan karena `.11` bermasalah.

Reachability dicek 2 lapis sebelum menulis checker: dari host server langsung (`curl`) dan dari
**dalam `forcad-celery-1`** (`python3 -c "import requests; ..."`) — keduanya sukses `200
{"ok":true}` ke `10.13.37.12:6789/api/healthz`.

## Build — tanpa patch (temuan positif, kontras dengan 4 dari 7 task sebelumnya)

`Dockerfile` dan `Dockerfile.imgsvc` **keduanya** punya blok:
```
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=linux go build ...
```
Sesuai preseden (greple/flagdrive di server utama), ini biasanya butuh strip manual karena
BuildKit tak tersedia. **Di VM ini TIDAK** — dicek eksplisit `docker buildx ls` di
`10.13.37.12` sebelum build:
```
NAME/NODE     DRIVER/ENDPOINT   STATUS    BUILDKIT   PLATFORMS
default*      docker                                
 \_ default    \_ default       running   v0.31.2    linux/amd64 (+4)
```
Builder `default` berstatus **running**, BuildKit v0.31.2 aktif secara native di daemon VM.
`docker compose build` (dijalankan APA ADANYA, tanpa modifikasi Dockerfile apa pun) sukses
bersih untuk keempat image (`web`, `imgsvc`, `leetdate`, `payments`), termasuk kedua blok
`--mount=type=cache` di atas — dicek di log build (`#50 [leetdate build 6/6] RUN
--mount=type=cache... DONE 98.6s`). **Tidak ada patch build server yang perlu dicatat untuk
task ini** — beda dari greple (Zig), flagdrive (BuildKit+href), funsplash (BuildKit+vendor
bravo). Payments (Python, `# syntax=docker/dockerfile:1.6` tapi tanpa `--mount`) & imgsvc juga
bersih.

Implikasi: server utama (`192.168.43.136`) dan VM tim (`10.13.37.12`) punya konfigurasi Docker
build yang **berbeda** (BuildKit ada/tidak) — relevan kalau task mendatang perlu membangun
image lain langsung di VM.

## Gate — lima kasus wajib

Dijalankan dari `forcad-celery-1` (`docker exec`), target `10.13.37.12:6789`:

```
check (live)                                        → 101
put   (live)                                         → 101
  stdout (flag_id) = {"h":"eagercomet4061"}
get   (flag_id di atas, flag sama)                   → 101
get   (state well-formed, handle "nosuchhandle999")  → 102
  pesan: "profil tak terambil (GET /api/users/{handle})"
  detail: equality assertion failed: 404 != 200
check (host mati, 10.13.37.250)                      → 104
  detail: ConnectionError/No route to host
```

**Ronde put/get kedua** (independen, flag berbeda, untuk memastikan bukan kebetulan/flaky):
```
put (live, flag "FLAG_second_round_zzZZ99=") → 101, flag_id = {"h":"gladfalcon7210"}
get (flag_id di atas)                        → 101
```

Log `leetdate` (`docker compose logs leetdate`) dicek sepanjang gate — semua request muncul
dengan status code yang cocok persis (`400` utk register-tanpa-display_name saat verifikasi
manual, `201`/`200`/`200`/`200`/`404` utk alur lengkap, tak ada `5xx` atau panic/stacktrace).

Setelah gate: `docker compose down -v` di VM (6 kontainer + 3 volume + network dihapus bersih,
dicek `docker ps -a` kosong utk `leet_date_service-*`). RAM server (`192.168.43.136`, yang tidak
pernah menjalankan stack ini) tak terpengaruh sama sekali — tetap ~6.8-6.9Gi available sebelum
dan sesudah, KARENA stack ini memang dijalankan penuh di VM, bukan di server.

## checker_timeout yang disarankan

**`checker_timeout: 15`**. `put()` melakukan 2 round-trip HTTP sekuensial (register, patch);
`get()` 1 round-trip; `check()` 1 round-trip. Semua request di gate live selesai puluhan ms
(`register` 85ms saat cold-start pertama karena bcrypt, sisanya <20ms — dicek langsung dari log
Gin `docker compose logs leetdate`). Backend Go+Gin+pgx pool, tanpa langkah berat (upload
foto/image-processing tak disentuh checker ini). 15 detik memberi margin >100x dari observasi
aktual, konsisten dengan usulan Task 7 (BEAM, juga ringan) untuk beban kerja serupa (2-3
round-trip per aksi).

## Reaper/TTL: `cleanup` container MENGHAPUS baris `users` — relevan untuk `round_time` nanti

`cleanup/cleanup.sh` menjalankan loop tak-terhingga: setiap `CLEANUP_INTERVAL_SEC` (=120 di
`docker-compose.yml`) menghapus `DELETE FROM users WHERE created_at < NOW() - (INTERVAL '1
minute' * ${CLEANUP_MAX_AGE_MIN})`, dengan `CLEANUP_MAX_AGE_MIN=15` (`docker-compose.yml:88`).
Karena flag hidup di kolom `bio` milik baris `users` yang dibuat `put()`, user (dan flag-nya)
**dihapus otomatis 15 menit setelah dibuat**, terlepas dari apakah sudah pernah di-GET atau
belum — pola reaper yang sama seperti d3pl0y/flagdrive (~12 menit) dan overeats, yang sudah
dicatat di Task 3/4/6 sebagai kendala config. **Menambah data point ke batasan lintas-task yang
sudah dicatat**: `round_time × flag_lifetime` untuk leet-date harus **≤ ~900 detik (15 menit)**
saat `config.enowars10.yml` disusun nanti (di luar scope task ini, Step 4 ditunda).

## Yang TIDAK diverifikasi / di luar cakupan

- **MUMBLE saat service hidup-tapi-salah** dan **CORRUPT saat flag ADA tapi DIUBAH** (mis. lawan
  menimpa `bio` user korban) — sama seperti dicatat lintas-task di Task 5 (⚠️), keduanya
  diverifikasi lewat pembacaan kode (PatchMe re-SELECT dari DB yang sama yang dibaca
  PublicProfile, jadi perubahan `bio` oleh siapa pun otomatis akan lolos ke `get()` — flag lama
  akan mismatch dan ter-CORRUPT dengan benar via `assert_eq(data.get("bio"), flag, ...,
  CORRUPT)`), bukan diuji langsung sebagai kasus gate ke-6 tambahan.
- Fitur lain servis (`photos`, `swipes`, `matches`, `conversations`, `premium`/`jwt`,
  websocket) — dibaca sekilas untuk memastikan tak relevan dengan kontrak PUT/GET flag
  (bio profil), tapi tidak diuji sama sekali oleh checker ini, sesuai brief (bio adalah jalur
  primer yang disebut, bukan alternatif `conversations`).
- `payments` (Bottle/Python) dan `imgsvc` — dibangun & dijalankan (dependency `depends_on` utk
  `leetdate`) tapi tak disentuh checker sama sekali (tak ada rute yang dipakai checker
  bergantung padanya secara langsung).
- Belum diuji: perilaku checker di bawah beban paralel (banyak `put`/`get` bersamaan) — gate
  hanya menguji sekuensial (2 ronde put/get + check).
- Config (`config.enowars10.yml`) dan status `UP` via engine round — sengaja tidak dikerjakan,
  sesuai resolusi ambiguitas brief.

## Concerns

1. **Tidak ada concern signifikan.** Ini task pertama dari 8 yang: (a) tidak butuh patch build
   server sama sekali, (b) gate lolos 101/101/101/102/104 tanpa iterasi ulang checker (draf
   pertama langsung benar) — berkat verifikasi manual live yang dilakukan SEBELUM menulis
   checker final, bukan sesudah gagal gate.
2. Reaper 15 menit (§"Reaper/TTL" di atas) perlu diingat eksplisit saat menyusun
   `config.enowars10.yml` — sudah dicatat di atas sbg data point, tapi menambahkan ke daftar
   layanan yg utang perhitungan `round_time` (sekarang: d3pl0y, flagdrive, overeats, leet-date).
3. Sama seperti seluruh sibling checker (dicatat konsisten sejak Task 3/4/5/6): flag_id yang
   BUKAN JSON sama sekali (bukan "JSON valid tapi handle tak ada") akan jatuh ke
   `status_for(ValueError) = MUMBLE`, bukan `CORRUPT` — perilaku harness/`decode_state`, bukan
   cacat checker ini; tidak masalah di produksi karena flag_id ForcAD selalu berasal dari `put()`
   sebelumnya (selalu JSON valid).
4. `display_name` diisi `A.rand_username()` (bukan `A.rand_text()`) supaya dijamin non-kosong
   by construction (1-64 char, tanpa whitespace-trim risk) — konsisten dengan pola field
   "pengisi" lain di sibling checker (funsplash `first_name`, Task 7).

## Evidence tambahan: cuplikan log `leetdate` selama gate

```
[GIN] ... 200 | GET      "/api/healthz"
[GIN] ... 400 | POST     "/api/register"     (verifikasi manual: tanpa display_name)
[GIN] ... 201 | POST     "/api/register"
[GIN] ... 200 | GET      "/api/me"           (auto-login, tanpa /api/login manual)
[GIN] ... 200 | PATCH    "/api/me"
[GIN] ... 200 | GET      "/api/users/chk_eqqtereu"
[GIN] ... 404 | GET      "/api/users/nosuchuser999"
[GIN] ... 200 | POST     "/api/login"        (verifikasi manual, tak dipakai checker resmi)
[GIN] ... 201 | POST     "/api/register"     (gate put run 1)
[GIN] ... 200 | PATCH    "/api/me"
[GIN] ... 200 | GET      "/api/users/eagercomet4061"   (gate get run 1)
[GIN] ... 404 | GET      "/api/users/nosuchhandle999"  (gate get bogus)
[GIN] ... 201 | POST     "/api/register"     (gate put run 2)
[GIN] ... 200 | PATCH    "/api/me"
[GIN] ... 200 | GET      "/api/users/gladfalcon7210"   (gate get run 2)
```

## File yang relevan

- `checkers/enowars10/leet-date/checker.py` (repo, commit-able) — satu-satunya file yang
  di-commit untuk task ini.
- `~/adlab/eno10/leet-date/` di server (`192.168.43.136`) DAN di VM (`10.13.37.12`) — rsync
  source, **tanpa modifikasi** (tak ada patch build yang perlu dipertahankan, beda dari
  greple/flagdrive/funsplash).
- `forcad-celery-1:/checkers/eno10_leet_date/checker.py` — dibiarkan terpasang (mode 755, owner
  uid 1000, dicek `nobody` bisa baca+eksekusi), sama seperti preseden sibling lain.
- `md5sum` file ter-deploy di celery vs file lokal yang di-commit (`bc05406`) dicek identik
  (`7d86c4d3106f276f6cbe0322cab9e660`) setelah commit — memastikan hasil gate di atas memang
  merefleksikan persis isi commit, bukan versi draft yang sudah berubah.
