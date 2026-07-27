# Task 6 Report: Checker `overeats` (:5432) — order note, Bearer

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(flag_id bogus)=102`, `check(host mati)=104`.
Commit: `2bc1cb0` — `feat(eno10): checker overeats (order note) + gate lolos` (branch
`enowars10-checkers`).

Servis Flask 5-container ini (nginx/web/livetrack/postgres/cleanup) **build mulus tanpa patch
Dockerfile apa pun** — satu-satunya hambatan infra bukan build, tapi **tabrakan port host 5432**
(lihat bawah), yang dipecahkan dengan pindah lokasi uji ke VM tim, BUKAN server host, menyimpang
dari preseden Task 2-5.

---

## Ringkasan alur

1. Baca brief + baca ULANG source asli nyata (`web/__init__.py`, `init.sql`,
   `crypto/notes_crypto.py`, `docker-compose.yml`, `nginx.conf`, `cleanup.sh`, `Dockerfile.*`)
   sebelum menulis checker — brief eksplisit menandai endpoint/field pembawa flag sbg
   *unconfirmed* dan bilang 5 task sebelumnya semua meleset di titik berbeda.
2. Tulis `checkers/enowars10/overeats/checker.py` dari template brief + koreksi (lihat bawah).
3. rsync source `OverEats/` laptop → server (`~/adlab/eno10/overeats/`) sesuai instruksi brief.
4. **Ditemukan tabrakan port**: host server (`192.168.43.136`) sendiri SUDAH bind `0.0.0.0:5432`
   (itu `forcad-postgres-1`, DB milik ForcAD sendiri) — nginx OverEats butuh publish
   `5432:80` persis di port yang sama. `docker compose up` di situ pasti gagal bind. Diputuskan
   pindah ke VM tim `10.13.37.11` ("athena") — opsi yang memang disebut brief ("run the service
   either on a team VM ... or on the server host attached to forcad_default") — karena di sana
   port 5432 kosong DAN publish port host asli tetap bisa dipakai apa adanya (tanpa perlu trik
   `forcad_default`-attach + IP-container-langsung yang dipakai Task 2-5, yang untuk servis
   nginx-fronted begini justru salah sasaran — lihat penjelasan lengkap di bawah).
5. rsync kedua server → VM `10.13.37.11:~/adlab/eno10/overeats/`, `docker compose up -d --build`
   dijalankan via SSH bertingkat (server→VM) di background, di-poll via notifikasi task
   (bukan blocking) — selesai, sukses tanpa patch Dockerfile apa pun.
6. Verifikasi bentuk request MANUAL via script Python (`requests`, disalin ke dalam container
   celery via `docker cp`, dijalankan `python3` di sana — vantage point sama dgn gate) SEBELUM
   checker resmi: register×2 (customer+restaurant), login×2, create-restaurant, place-order,
   create-note, get-notes (token sendiri DAN token restoran lain), order/notes nonexistent,
   order-details tanpa auth — semua dicocokkan ke `checker.py` sebelum gate resmi.
7. Deploy checker ke celery (`~/adlab/forcad/checkers/eno10_overeats/checker.py`, mode 755),
   `md5sum` identik vs repo lokal, sanity-import di dalam container sebagai user `nobody`.
8. Gate 5-langkah — semua lolos exit code yang diminta.
9. Teardown (`docker compose down -v` di VM), verifikasi container hilang, port 5432 balik
   kosong, memory VM & server balik ke/atas baseline.
10. Commit HANYA `checkers/enowars10/overeats/checker.py`. `forcad/config.enowars10.yml` TIDAK
    disentuh, TIDAK ada ronde engine dijalankan (sesuai instruksi override task).

---

## Keputusan infra: kenapa VM tim, bukan server host (menyimpang dari preseden Task 2-5)

Task 2 eksplisit memilih server host + `forcad_default` **atas** VM tim, dengan alasan VM tim
cuma sisa ~2.1GB available (vs host 6.2GB) — preseden itu diikuti Task 3/4/5 tanpa masalah.
Untuk `overeats`, dua hal baru muncul bersamaan yang membuat pola itu tidak bisa dipakai apa
adanya:

1. **Tabrakan port nyata, bukan cuma teoretis** (sudah diantisipasi brief: "watch for a port
   collision if anything else on the host already binds 5432"). Dicek `ss -tlnp` di server:
   `forcad-postgres-1` sudah `0.0.0.0:5432->5432/tcp`. `docker compose up` OverEats di host
   akan gagal bind nginx-nya (`ports: ["5432:80"]` di `docker-compose.yml`) — bukan soal
   "servis salah paham port", tapi genuinely tak ada slot host yang bisa dipakai di mesin itu.
2. **Topologi nginx-fronted mengubah makna "IP container di forcad_default"**. Pola Task 2-5:
   tempel SEMUA container compose ke `forcad_default` (via `docker-compose.override.yml`), lalu
   gate ke `<ip-container>:<PORT>` — ini valid HANYA kalau container yang dituju benar2
   mendengarkan pada `PORT` itu SECARA INTERNAL. Untuk `overeats`, `PORT=5432` adalah port
   **host-published** nginx (`nginx.conf`: `listen 80;` — internal-nya 80, BUKAN 5432). Kalau
   nginx OverEats ditempel ke `forcad_default` lalu digate ke `<ip-container-nginx>:5432`,
   koneksi akan GAGAL (connection refused) — tak ada apa pun di container itu yang mendengarkan
   5432. Satu-satunya cara membuat `PORT=5432` (sesuai instruksi brief: "do not correct it")
   benar2 nyambung adalah lewat publish port HOST asli (`hostPort:containerPort` = `5432:80`),
   dan itu makna "port eksternal" yang sebenarnya dimaksud brief — persis seperti nanti di round
   sungguhan, checker akan bicara ke `<vulnbox-ip>:5432` di level jaringan vulnbox, bukan ke IP
   docker-network internal manapun.

Dengan dua hal itu bersamaan, pilihan paling bersih & paling jujur mereproduksi kondisi
"eksternal" adalah pindah ke mesin di mana port 5432 memang kosong di level host — VM tim.
Dicek dulu (`ss -tln` di kedua VM): **`10.13.37.11` DAN `10.13.37.12` sama2 kosong di 5432**
(container Fase-1 yang ada, mis. `shetcode-database-1`/`birthdaygram-postgres-1`, dengar 5432
HANYA di jaringan compose sendiri, tak dipublish ke host). Dipilih `.11` ("athena"). Konektivitas
celery→VM dikonfirmasi lebih dulu (`curl telnet://10.13.37.11:22` dari dalam container
`forcad-celery` → TCP connect sukses + banner SSH diterima, sebelum rsync/build apa pun
dijalankan) — bukan asumsi.

**Trade-off yang diterima secara sadar**: RAM VM tim jauh lebih ketat (`2.9Gi` total, `~2.1Gi`
available, sudah dipakai 7 container Fase-1) dibanding server host (`6.2Gi` available). Diterima
krn stack OverEats memang ringan (nginx-alpine, postgres-alpine, 1 binary Go kecil, Flask+gunicorn
4-worker, cleanup cuma loop `psql`) — dikonfirmasi empiris: `free -h` di VM turun dari `2.1Gi` ke
`1.9Gi` available SELAMA stack hidup (~200MB dipakai 5 container), jauh di bawah batas, dan balik
ke `2.1Gi` persis sesudah teardown. Tak ada patch `docker-compose.yml`/network apa pun yang perlu
dipertahankan di server — cukup rsync manual biasa + `docker compose up/down` apa adanya, LEBIH
SEDERHANA dari pola override Task 2-5 (krn tak butuh trik attach-network sama sekali).

**Catatan operasional kecil ditemukan**: SSH bertingkat (server → VM) mewarisi masalah PATH
kosong yang sama di KEDUA hop, bukan cuma hop pertama — percobaan pertama
(`ssh server "ssh vm '...'"` tanpa `export PATH=...` di level OUTER) gagal `command not found:
ssh` (exit 127) krn shell non-interaktif di server sendiri tak punya PATH utk menemukan binary
`ssh`-nya sendiri. Perbaikan: set `export PATH=...` di KEDUA lapis SSH, bukan cuma yang
menyentuh Docker.

---

## Perubahan bentuk request terhadap brief

Brief benar soal pola dasar (`POST /api/register`/`/api/login` → `Authorization: Bearer <token>`)
dan benar menyebut resource pembawa flag adalah "order note" — tapi brief eksplisit menandai
endpoint/field-nya sbg *unconfirmed*, dan bentuk konkretnya di `web/__init__.py` ternyata berbeda
cukup jauh dari draft kode brief di beberapa titik kritis.

### 1. KRITIS — `POST /api/orders` tidak pernah menerima/menyimpan field `note`

`web/__init__.py:290-318` (`place_order`) hanya membaca `restaurant_id`, `items`,
`special_instructions` dari body — field `note` yang dikirim draft brief langsung ke endpoint ini
akan **diam-diam diabaikan** (tak pernah masuk statement `INSERT INTO orders`, dan tabel `orders`
di `init.sql:30-40` memang tak punya kolom untuk itu). Flag disimpan lewat endpoint **terpisah**:
`POST /api/orders/<order_id>/notes` (`web/__init__.py:508-537`, `create_note`), body `{"note":
...}`, ke tabel **terpisah** `order_notes` (`init.sql:63-70`) — persis seperti diarahkan brief
sendiri ("Konfirmasi path note terhadap init.sql (order_notes)"). Dikonfirmasi empiris (lihat
evidence di bawah): `POST /api/orders` balas `{"order_id": 2}` (TANPA note apa pun tersimpan),
lalu `POST /api/orders/2/notes` balas terpisah `{"note_id": 2}`.

### 2. KRITIS — `place_order` mewajibkan `restaurant_id` yang valid, servis tak menyemai satu pun

`web/__init__.py:301-303`: `rest = db_query("SELECT id FROM restaurants WHERE id = %s", ...); if
not rest: return 404`. `init.sql` **tidak** meng-`INSERT` satu baris pun ke `restaurants` — jadi
`restaurant_id` mana pun akan 404 kecuali checker membuat restoran dulu. Membuat restoran
(`POST /api/restaurants`, `web/__init__.py:229-247`) mewajibkan akun ber-`role` PERSIS
`"restaurant"` (baris 232: `if g.current_user['role'] != 'restaurant': return 403`), sedangkan
`register()` men-default role ke `"customer"` bila field `role` tak dikirim (baris 177). Draft
brief cuma register SATU akun (implisit customer) dan tak pernah membuat restoran — `put()` yang
ditulis membuat **akun kedua** (`role: "restaurant"`) khusus utk `POST /api/restaurants`, murni
sbg alat bantu memenuhi FK, sebelum akun customer memesan.

### 3. KRITIS — tidak ada rute `GET /api/orders/<id>` generik; note dibaca lewat rute LIST terpisah

Draft brief menebak `GET /api/orders/{st['o']}` mengembalikan note di body-nya. Rute itu **tidak
ada sama sekali** di `web/__init__.py` — yang ada hanya `/api/orders/<id>/details` (metadata order:
items/status/total_price, TANPA note apa pun, baris 365-412) dan `/api/orders/<id>/notes` (baris
539-587). Rute yang benar (`GET /api/orders/<order_id>/notes`) membalas **list semua note milik
order itu**: `{"notes": [{"note_id", "note", "created_at"}, ...]}` — bukan objek tunggal — jadi
`get()` mencari entry dgn `note_id` yang cocok dgn state, baru menge-assert field `"note"`-nya,
bukan asumsi objek tunggal atau substring `r.text` mentah.

### 4. Nama field balasan berbeda dari asumsi generik brief

- `POST /api/orders` balas `order_id` (`web/__init__.py:318`), bukan `id`. Fallback brief
  `r.json().get("id") or r.json().get("order_id")` kebetulan tetap benar krn fallback-nya, tapi
  `"id"` memang tak pernah ada.
- `POST /api/orders/<id>/notes` balas `note_id` (baris 537), status 201.
- `POST /api/restaurants` balas `restaurant_id` (baris 247), status 201 — field ini sama sekali
  tak disebut di draft brief (krn draft brief tak tahu soal FK restaurant_id di awal).

### 5. Perilaku halus lapisan crypto — kenapa `get()` HARUS pakai token customer yang sama

`crypto/notes_crypto.py`: `encrypt_note()` membungkus `owner_id` di DALAM plaintext terenkripsi
(`f"owner={owner_str}|note={note_text}"`), dan `decrypt_note(..., expected_owner=...)`
mengembalikan **`None` secara diam-diam** (bukan exception) kalau `actual_owner != expected_owner`
(baris 60-61). `get_notes()` (`web/__init__.py:563-587`) memanggil `decrypt_note` dengan
`expected_owner=g.current_user['id']` — jadi **pemanggil GET notes yg berbeda dari pembuat note,
walau "berhak" secara access-control** (restoran pemilik order, atau driver), akan dapat list
notes **kosong** utk order itu, bukan error apa pun. Dikonfirmasi empiris (lihat evidence): token
restoran pemilik order yang sama balas `{"notes": []}` (200 OK, bukan 403), sedangkan token
customer pembuat note balas note-nya utuh. `get()` checker sengaja memakai token customer dari
state `put()`, bukan token lain, persis krn temuan ini.

### 6. `check()` — brief tak menentukan endpoint eksplisit, dipilih dari source

Draft brief menebak `GET "/"` + assert `status<500`. Dipilih `GET /api/health`
(`web/__init__.py:824-830`) sbg ganti — endpoint ini betul2 menyentuh DB (`db_query("SELECT
1")`) sebelum balas `200 {"status":"healthy","service":"OverEats"}` atau `500
{"status":"unhealthy",...}`, jadi sinyal liveness yang jauh lebih berarti drpd Jinja
`index.html` statis (`templates/index.html`, tak pernah menyentuh DB). Konsisten dgn preseden
signmemaybe (`/api/info`) & flagdrive (`/api/health`): dua assert terpisah (status code DAN field
JSON), bukan cuma status code mentah.

---

## Detail arsitektur overeats (konteks utk task berikutnya bila masuk roster resmi)

- **Reaper 12 menit**: `init.sql:106-257`, fungsi `cleanup_old_data()`,
  `cutoff := NOW() - INTERVAL '12 minutes'` — dijalankan oleh container `cleanup` terpisah
  (`cleanup.sh`, loop `psql -c "SELECT cleanup_old_data();"` tiap 60 detik) **DAN** oleh thread
  in-process di `web` (`web/__init__.py:136-153`, `cleanup_thread` daemon, `time.sleep(60)` lalu
  panggil fungsi SQL yang sama) — dua jalur redundan ke fungsi SQL yang sama, dilindungi
  `pg_try_advisory_xact_lock` (baris 110) supaya tak race satu sama lain. Menguatkan pola
  cross-task yang sudah dicatat (Task 3/4: d3pl0y/flagdrive juga ~12 menit): kalau
  `round_time × flag_lifetime` didesain nanti, servis ini exactly sama dgn preseden itu, BUKAN
  kasus baru spt signmemaybe (720 detik/12 menit jg kebetulan sama, tapi via cron container
  bukan in-process — overeats malah dobel-jalur).
- **`checker_timeout` — TAK disebut di brief, diusulkan `30`**: `put()` checker ini melakukan
  **7 request HTTP berurutan** (register customer, login customer, register restoran, login
  restoran, create restaurant, place order, create note) — lebih dari dua kali lipat put()
  signmemaybe (3 request, diusulkan brief `25`) atau greple/flagdrive (~3-4 request). Diusulkan
  `checker_timeout: 30` sbg titik awal saat registrasi config nanti, dgn margin utk 7 round-trip
  + start-up race gunicorn (lihat bawah) di kondisi jaringan lebih lambat drpd lab ini.
- **Race start-up gunicorn/postgres teramati, self-healing, TAK berdampak ke checker**: pada
  `docker compose up` pertama, `web` (gunicorn `-w 4`) boot SEBELUM `postgres` siap menerima
  koneksi (`docker-compose.yml` cuma `depends_on: [postgres]` tanpa
  `condition: service_healthy`) — `ThreadedConnectionPool` yang diinisialisasi di level modul
  (`web/__init__.py:54-58`) langsung gagal connect saat import, bikin worker pertama crash sekali
  (`OperationalError: connection to server at "postgres" ... Connection refused`). Gunicorn
  master otomatis reboot worker baru begitu ada yang gagal boot (`Worker failed to boot` →
  `Booting worker` lagi) — begitu Postgres selesai jalankan `init.sql`, gelombang worker
  berikutnya sukses tanpa intervensi apa pun. Dikonfirmasi `/api/health` balas 200 sehat beberapa
  detik sesudahnya. Ini murni race Docker Compose tanpa healthcheck-gating, **bukan bug servis**
  dan **bukan bug checker** — dicatat sbg observasi arsitektur (kalau nanti round pertama
  kebetulan menyenggol jendela race ini sesaat setelah container start, `check()` bisa MUMBLE
  sesaat, self-heal dalam hitungan detik).
- **Enkripsi note**: AES-128/192/256-CBC (panjang tergantung `ENCRYPTION_KEY_FILE`, 16 byte hex →
  AES-128) + HMAC-SHA256 terpisah (bukan AEAD), IV acak per note, kunci dibaca dari file yang
  di-generate sekali & disimpan di volume `keydata` (persisten lintas restart container `web`
  selama volume tak dihapus) — checker tak bergantung pada detail ini sama sekali (semua lewat
  API, bukan crypto langsung), dicatat murni sbg observasi.
- **LiveTrack** (`livetrack/main.go`, protokol biner custom via `/api/livetrack/*` proxy) & rute
  `/api/notes/export`+`/api/notes/import` (blob note bisa diekspor/diimpor via `X-Internal-Auth`
  yg di-strip nginx utk klien eksternal, `nginx.conf:13`) **tidak dieksplorasi mendalam** —
  brief menyebut "chat message" sbg alternatif hipotesis lokasi flag, tapi source
  (`create_note`/`get_notes`/`order_notes`) sudah cukup jelas dan pasti sbg mekanisme resmi;
  `chat_messages` (tabel terpisah, `init.sql:54-60`) dipakai utk pesan driver↔customer soal
  pengiriman, tak berkaitan dgn flag sama sekali (tak ada endpoint yg menaruh flag di sana).
  Permukaan ini dicatat sbg kemungkinan lokasi vuln lain, di luar scope checker note.

---

## Evidence gate (exact commands + output)

Lokasi servis: VM tim `reky@10.13.37.11` ("athena"), `~/adlab/eno10/overeats/`, docker compose
ASLI tanpa override apa pun. Gate dijalankan dari `forcad-celery` (server `192.168.43.136`)
lewat `docker exec`, target IP `10.13.37.11`, port `5432` (host-published asli, BUKAN IP
container internal).

### Build
```
$ ssh reky@10.13.37.11 'cd ~/adlab/eno10/overeats && docker compose up -d --build'
...
 Container overeats-postgres-1   Started
 Container overeats-livetrack-1  Started
 Container overeats-cleanup-1    Started
 Container overeats-web-1        Started
 Container overeats-nginx-1      Started
BUILD_SUCCESS (dijalankan via run_in_background, di-poll lewat notifikasi task — tanpa blocking)
```
`docker compose ps` sesudahnya: 5 container `Up` (`nginx`, `web`, `livetrack`, `postgres`,
`cleanup`), `overeats-nginx-1` publish `0.0.0.0:5432->80/tcp` persis spt `docker-compose.yml`.

### Verifikasi manual (dari dalam celery, SEBELUM gate resmi — script Python via `docker cp`)
```
--- register customer ---        http_code=201  {"token": "...", "user_id": 1}
--- login customer ---            http_code=200  {"role": "customer", "token": "...", "user_id": 1}
--- register restaurant ---       http_code=201  {"token": "...", "user_id": 2}
--- login restaurant ---          http_code=200  {"role": "restaurant", "token": "...", "user_id": 2}
--- create restaurant ---         http_code=201  {"restaurant_id": 1}
--- place order ---               http_code=201  {"order_id": 1}
--- create note ---               http_code=201  {"note_id": 1}
--- get notes (own customer) ---  http_code=200  {"notes": [{"created_at": "...", "note":
                                   "ENOTESTFLAGoverEatsManualVerifyXEQUWRVC=", "note_id": 1}]}
                                   match found: True flag in note: True
--- notes, order nonexistent ---  http_code=404  {"error": "Order not found"}
--- order details, no auth ---    http_code=401  {"error": "Authentication required"}
--- get notes as restaurant ---   http_code=200  {"notes": []}   (dikonfirmasi: decrypt_note
                                   owner-check menyaring diam2, BUKAN 403 — lihat §5 di atas)
```

### Deploy checker
```
~/adlab/forcad/checkers/_lib/adlab_eno.py                (sudah ada, TIDAK diubah)
~/adlab/forcad/checkers/eno10_overeats/checker.py         (baru, mode 755, owner reky:reky)
```
`md5sum` identik vs repo lokal (`747132e9f625f77f0f20409967114308`, keduanya). Sanity-import
sbg user `nobody`: `python3 -c "import checker"` (sys.path diarahkan manual ke
`/checkers/eno10_overeats` + `/checkers/_lib`) → `import OK 5432`, tanpa error.

### Gate run (persis versi checker.py yang di-commit)
```
$ C=$(docker ps -qf name=forcad-celery); IP=10.13.37.11

$ docker exec $C /checkers/eno10_overeats/checker.py check $IP; echo "check_exit=$?"
check_exit=101

$ FLAG='ENOTESTFLAGoverEatsGate1928374650XYZW='
$ docker exec $C /checkers/eno10_overeats/checker.py put $IP "" "$FLAG" 0 >/tmp/oe_put.out 2>/tmp/oe_put.err
$ echo "put_exit=$?"
put_exit=101
$ cat /tmp/oe_put.out
{"t":"0ed7dc1531d2fc7d94a552cd9ba9e1e1267d5850f4a61ccf1ba4f78962ebac42","o":"2","n":"2"}

$ FID=$(cat /tmp/oe_put.out)
$ docker exec $C /checkers/eno10_overeats/checker.py get $IP "$FID" "$FLAG" 0; echo "get_exit=$?"
get_exit=101

$ BOGUS='{"t":"0ed7dc1531d2fc7d94a552cd9ba9e1e1267d5850f4a61ccf1ba4f78962ebac42","o":"999999999","n":"1"}'
$ docker exec $C /checkers/eno10_overeats/checker.py get $IP "$BOGUS" "$FLAG" 0 >/tmp/oe_corrupt.out 2>/tmp/oe_corrupt.err
$ echo "corrupt_exit=$?"
corrupt_exit=102
$ cat /tmp/oe_corrupt.err
[__main__.Checker.get:98] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec $C /checkers/eno10_overeats/checker.py check 10.13.37.99 >/tmp/oe_down.out 2>/tmp/oe_down.err
$ echo "down_exit=$?"
down_exit=104
$ cat /tmp/oe_down.err
ConnectionError(MaxRetryError("HTTPConnectionPool(host='10.13.37.99', port=5432): Max retries
exceeded with url: /api/health (Caused by NewConnectionError('...Failed to establish a new
connection: [Errno 113] No route to host'))"))
```

Semua exit code sesuai yang diminta: **101 / 101 / 101 / 102 / 104**.

Catatan mekanisme "bogus flag_id" (sama seperti Task 3/4/5): bogus HARUS JSON *valid* dgn isi
salah (di sini: token asli + `order_id=999999999` yg nonexistent, dikonfirmasi 404 lewat
verifikasi manual di atas), BUKAN string bukan-JSON — kalau bukan-JSON, `A.decode_state`
melempar `ValueError` yg lolos ke `except Exception as e: cquit(A.status_for(e), ...)` di
`__main__`, dan `status_for` memetakan `ValueError` → `MUMBLE` (103), BUKAN `CORRUPT` (102) yg
diminta.

FLAG yang dipakai gate resmi (`...Gate1928374650XYZW=`) BERBEDA dari FLAG verifikasi manual
(`...ManualVerifyXEQUWRVC=`) — bukti gate resmi benar2 dieksekusi ulang dgn kredensial baru,
bukan reuse hasil verifikasi manual.

### Teardown (setelah gate lolos)
```
$ ssh reky@10.13.37.11 'cd ~/adlab/eno10/overeats && docker compose down -v'
 Container overeats-nginx-1 Removed
 Container overeats-web-1 Removed
 Container overeats-livetrack-1 Removed
 Container overeats-cleanup-1 Removed
 Container overeats-postgres-1 Removed
 Network overeats_overeats-net Removed
 Volume overeats_pgdata Removed
 Volume overeats_keydata Removed
teardown_exit=0

$ docker ps -a --format "{{.Names}}" | grep -i overeats || echo "no overeats containers"
no overeats containers
$ ss -tln | grep 5432 || echo "port 5432 free"
port 5432 free
$ free -h   # VM 10.13.37.11
available: 2.1Gi   (sama dgn baseline sblm build: 2.1Gi)

$ docker network inspect forcad_default --format "{{range .Containers}}{{.Name}} {{end}}"
# (server) 15 anggota — TIDAK berubah (overeats tak pernah ditempel forcad_default sama sekali
# di skema deployment ini, konsisten dgn keputusan §"Keputusan infra" di atas)
$ free -h   # server 192.168.43.136
available: 6.2Gi   (sama/di atas baseline)
```

---

## File yang diubah/dibuat

- **`checkers/enowars10/overeats/checker.py`** (baru, executable, 118 baris) — satu-satunya file
  yang di-commit, sesuai instruksi override task.
- **TIDAK diubah**: `deploy/enowars10-deploy.sh` (tak dipakai sama sekali utk task ini — dipakai
  pola rsync+`docker compose` manual biasa di VM tim krn topologi & tabrakan port yang beda dari
  asumsi skrip; skrip itu sendiri tetap di luar scope, tak disentuh), `forcad/config.enowars10.yml`
  (registrasi ditunda, sesuai instruksi eksplisit), `checkers/enowars10/_lib/*` (di-reuse apa
  adanya), `checkers/requirements.txt` server (`~/adlab/forcad/checkers/requirements.txt` — tak
  perlu dep baru; checker cuma pakai stdlib `sys`/`pathlib` + `checklib`/`requests`/`adlab_eno`
  yg sudah ada — dikonfirmasi `requests` walau tak eksplisit tercantum di file itu, sudah
  tersedia transitif lewat instalasi `checklib`, terbukti jalan tanpa error import apa pun di
  gate), `docker_config/celery/Dockerfile.fast` (tak disentuh, tak perlu CUSTOMIZE block apa pun).

Sisi server/VM (tidak dicommit, konsisten dgn pola checker lain):
- `~/adlab/forcad/checkers/eno10_overeats/checker.py` (server, dibiarkan terpasang di celery).
- `~/adlab/eno10/overeats/` (server) — rsync source, dipertahankan utk rebuild berikutnya.
- `~/adlab/eno10/overeats/` (VM `10.13.37.11`) — rsync source + **image Docker hasil build**
  (`overeats-web`, `overeats-livetrack`, `overeats-nginx`) dibiarkan ter-cache di VM (tak
  di-`docker image rm`/`prune`) — containers/network/volume SUDAH diturunkan penuh (`down -v`),
  jadi tak ada RAM yg dipakai, cuma disk (VM masih longgar: 12G available dari 20G sblm test).
  Kalau task berikutnya butuh VM ini utk servis lain dan disk jadi masalah, image ini aman
  dihapus (`docker image prune` atau `docker rmi` eksplisit).
- **Tidak ada** patch `Dockerfile`/`docker-compose.yml`/override apa pun yg perlu dipertahankan
  di server maupun VM — build & compose berjalan 100% dari source asli tanpa modifikasi.
- Laptop source (`~/workspaces/cylab/ctf/.../OverEats/`) — **tidak disentuh sama sekali**, hanya
  dibaca (`Read` tool) lalu di-rsync (read-only dari perspektif rsync sbg source).

---

## Self-review

- **Faithfulness ke brief**: struktur `Checker(BaseChecker)`, method `check/put/get`, exception
  handling `__main__` (Checker construction DI LUAR try) dipakai verbatim persis draft brief.
  Header `Authorization: Bearer`, endpoint dasar `/api/register`/`/api/login` SEMUA benar sesuai
  brief. Deviasi ADA di: (a) endpoint/field pembawa note (`POST /api/orders/<id>/notes`, bukan
  field `note` inline di `POST /api/orders`) — brief sendiri sudah menandai ini *unconfirmed* dan
  minta konfirmasi; (b) kebutuhan akun restoran+restaurant_id sbg prasyarat FK yg tak disebut
  draft brief sama sekali; (c) rute baca note (`GET .../notes`, list, bukan `GET
  /api/orders/{id}` tunggal). Semua dikonfirmasi empiris via script verifikasi manual SEBELUM
  ditulis ke checker resmi, lalu lolos gate LIVE dgn kredensial BEDA dari verifikasi manual.
- **Tidak ada state palsu**: setiap exit code & output di atas hasil run asli berurutan dlm satu
  sesi; token/order_id/note_id di evidence gate BERBEDA dari verifikasi manual (order_id 2 vs 1,
  dst — bukti user_id/order/note counter servis memang bertambah dari sesi verifikasi
  sebelumnya, bukan reuse).
- **Klasifikasi status disengaja per-kasus**: `check()`/`put()` pakai `Status.MUMBLE` utk semua
  kegagalan langkah (servis "hidup tapi salah", bukan flag hilang); `get()` pakai `Status.CORRUPT`
  utk status code bukan-200, note_id tak ditemukan, ATAU flag tak ada di field note (semua berarti
  "flag sudah tak bisa diambil lagi lewat jalur resminya", sesuai definisi CORRUPT). Fallback
  `status_for()` di `__main__` menangani DOWN (koneksi) & MUMBLE (ValueError/KeyError/dst) di
  luar assert eksplisit — dikonfirmasi via kasus dead-host (104) & bogus-tapi-valid-JSON (102).
- **Genuine round-trip**: `get()` mengambil `note` dari field JSON yang sudah di-parse
  (`target.get("note", "")`) pada entry yang dicocokkan lewat `note_id` tersimpan di state —
  bukan echo dari request GET itu sendiri (GET tak mengirim flag sama sekali), dan bukan lewat
  jalur yg tetap lolos kalau flag di-overwrite (kalau attacker mengganti isi note dgn note_id yg
  sama, `assert_in` akan gagal krn isi field `note` sudah beda; kalau note dihapus, `target is
  not None` akan gagal duluan).
- **Isolasi perubahan**: TIDAK ada patch Dockerfile/source servis yg perlu dipertahankan (build
  mulus dari awal, servis ini kebetulan paling "bersih" secara build dari 5 servis yg sudah
  dikerjakan); laptop source (bank-soal repo terpisah) tidak tersentuh selain dibaca.
- **Commit bersih**: `git add` eksplisit 1 file, `git status --short` dicek sebelum & sesudah
  commit — hanya `checkers/enowars10/overeats/checker.py` ter-stage (`.omc/` sudah ada sejak
  awal sesi, tidak ikut).
- **Resource VM/server**: `overeats` di-teardown penuh (`docker compose down -v`) di VM tim,
  port 5432 balik kosong, memory VM & server balik ke/di atas baseline masing2, tidak ada
  container/volume nyisa. Baseline diambil SEBELUM containers hidup utk perbandingan yg fair.

## Kekhawatiran (bukan blocker)

- **Keputusan lokasi deployment (VM tim, bukan server host) adalah penyimpangan disengaja dari
  preseden Task 2-5**, dipicu murni oleh tabrakan port 5432 di server (`forcad-postgres-1` sudah
  memakainya) DAN topologi nginx-fronted yg baru pertama kali muncul di batch ini (lihat detail
  penuh di §"Keputusan infra" di atas). Ini keputusan uji LOKAL saja — di round sungguhan nanti,
  `overeats` akan jalan di vulnbox tim (bukan di server ad-platform ini), jadi tabrakan port ini
  TIDAK relevan lagi sbg constraint produksi. Dicatat sbg preseden kalau servis berikutnya
  (Task 7-11) kebetulan juga nginx-fronted dgn port host yg bentrok — pola "pindah ke VM tim +
  publish port asli" di laporan ini bisa dipakai ulang.
- **RAM VM tim jauh lebih ketat** (2.9Gi total) drpd server (15Gi total) — utk servis ini terbukti
  cukup (dikonfirmasi empiris, available tak pernah turun di bawah ~1.9Gi), tapi kalau servis
  berikutnya yg juga butuh VM tim jauh lebih berat, ini bisa jadi constraint nyata (bukan cuma
  teoretis spt dicatat Task 2).
- **`assert_eq(r.status_code, 200, ..., Status.CORRUPT)` di `get()` menyamaratakan semua non-200**
  (401 tanpa/token beda, 404 order salah, 5xx transien) jadi CORRUPT — preseden identik persis di
  ke-4 checker sebelumnya (greple/d3pl0y/flagdrive/signmemaybe), sengaja dibiarkan konsisten.
- **File temp kecil tersisa** di dalam container `forcad-celery` (`/tmp/manual_verify.py`,
  disalin via `docker cp` sbg root, tak berhasil dihapus dgn permission user biasa saat cleanup)
  — tak berbahaya (script Python murni baca-API, tak menyentuh kredensial nyata), tapi dicatat
  sbg housekeeping minor yg belum tuntas; akan hilang sendiri kalau container `forcad-celery`
  suatu saat direstart/dibuat ulang.
- **`checker_timeout: 30` (diusulkan, BELUM diterapkan)** — dicatat verbatim di atas (§"Detail
  arsitektur") utk dipakai saat registrasi config nanti; belum divalidasi terhadap jaringan round
  sungguhan (cuma diuji di lab dgn latensi VM-tim↔server yg sangat rendah).
- **`rand_username()`/`rand_password()`** (dari `adlab_eno`, dipakai apa adanya) — risiko kolisi
  username teoretis sama spt task-task sebelumnya (register balas 409, assert `//100==2` MUMBLE
  dgn benar, bukan crash) — tidak diubah, konsisten dgn precedent. Di sini risikonya 2x lipat
  (dua akun per `put()`, customer+restaurant) tapi masih sangat kecil scr statistik.
- Permukaan `/api/notes/export`+`/api/notes/import`, `/api/livetrack/*`, dan interaksi
  driver/delivery (`deliveries`, `chat_messages`) **tidak dieksplorasi mendalam** — di luar
  scope checker note tunggal ini, dicatat sbg permukaan lain yg mungkin jadi vuln resmi servis
  (mis. `export`/`import` blob HMAC-terverifikasi tapi lewat token siapa pun yg tahu blobnya,
  atau proxy `/api/livetrack/raw` yg meneruskan frame biner mentah tanpa validasi opcode).
