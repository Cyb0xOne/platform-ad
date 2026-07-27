# Task 3 Report: Checker `d3pl0y` (:2553) — object store, Basic auth

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(flag_id bogus)=102`, `check(host mati)=104`.
Commit: `bf26cbe` — `feat(eno10): checker d3pl0y (object store) + gate lolos` (branch `enowars10-checkers`).

Hare-VM build **berhasil tanpa patch** (berbeda dari greple/Zig di Task 2 yang butuh 2 patch) —
tidak ada BLOCKED, tidak perlu fallback "skip VM stage".

---

## Ringkasan alur

1. Baca brief + baca ULANG source asli nyata (`api.py`, `app.py`, `web.py`, `internal.py`,
   `config.py`, `db.py`) sebelum menulis checker — brief eksplisit bilang field name-nya
   recon-derived, dan ternyata 3 hal meleset (lihat bawah).
2. Tulis `checkers/enowars10/d3pl0y/checker.py` dari template brief + 3 koreksi.
3. rsync source `d3pl0y/` dari laptop ke server (`~/adlab/eno10/d3pl0y/`).
4. Deploy: attach ke `forcad_default` (pola Task 2 — service HTTP ringan di host, bukan VM tim),
   `docker compose up -d --build`. Build Hare-VM (multistage: debian sid + toolchain `hare` +
   clone `hare-sqlite` dari git.sr.ht) makan waktu tapi **sukses murni**, tidak perlu patch service
   apa pun (kontras dengan greple yang butuh 2 patch Zig).
5. Konfirmasi reachable dari celery (`docker exec $C curl -m5 192.168.0.17:2553/`).
6. Curl manual (dari DALAM container celery, vantage point yang sama dgn gate) ke
   `/api/user/register`, PUT/GET `/api/user/{owner}/{name}`, plus kasus wrong-auth &
   wrong-object-name — semua dicocokkan ke checker.py SEBELUM gate resmi dijalankan.
7. Deploy checker ke celery (host path langsung, BUKAN `docker exec mkdir`, lihat catatan Task 2
   soal `uid=65534 nobody` — tetap berlaku, dipakai lagi di sini).
8. Gate 5-langkah — semua lolos exit code yang diminta.
9. Diff `checker.py` lokal vs yang di-deploy di server — identik (tidak ada file drift).
10. Teardown `d3pl0y` (`docker compose down -v`), verifikasi container hilang, network
    `forcad_default` balik ke 15 anggota semula, memory available balik ke baseline.
11. Commit HANYA `checkers/enowars10/d3pl0y/checker.py`. `forcad/config.enowars10.yml` TIDAK
    disentuh, TIDAK ada ronde engine dijalankan (sesuai instruksi override task).

---

## Perubahan bentuk request terhadap brief (3 hal, semua diverifikasi baca source + curl nyata)

Brief Step 1 eksplisit bilang field name recon-derived dan perlu diiterasi. Setelah baca
`app.py`/`api.py` asli, 3 asumsi brief ternyata salah:

### 1. Endpoint kontrak hidup di prefix `/api`, bukan root

`app.py`:
```python
app.mount("/api", api)
app.mount("/web", web)
```
Brief pakai `s.post("/user/register")` dan `s.put(f"/user/{u}/{name}")` — path TANPA prefix.
Karena `api` (yang berisi `/user/register`, `/user/{owner}/{name}`) di-mount di `/api`, path
sebenarnya adalah `/api/user/register` dan `/api/user/{owner}/{name}`. Tanpa prefix, FastAPI
routing di top-level app tidak match apa pun di bawah `/api`, jatuh ke 404. Dikoreksi di ketiga
pemanggilan (register, PUT, GET).

### 2. Body register harus form-urlencoded, bukan JSON

`api.py`:
```python
@router.post("/user/register")
async def register(request: Request, username: Annotated[str, Form()] = ""):
```
Brief pakai `s.post("/user/register", json={"username": u})`. `Annotated[str, Form()]` mem-bind
dari body `application/x-www-form-urlencoded`/`multipart`, BUKAN dari JSON body — kalau dikirim
sebagai `json=`, FastAPI tidak menemukan field `username` sama sekali (default `""`), lalu
`internal.register()` menolak username kosong (`USERNAME_RE` tak match `""`) → `400`. Dikoreksi
jadi `s.post("/api/user/register", data={"username": u})` (curl manual mengonfirmasi: `201
Created`, cocok).

### 3. Respons register = teks polos berisi token, BUKAN JSON `{"token": ...}`

`api.py`:
```python
token = await internal.register(request, username)
return Response(content=token, status_code=201)
```
Ini `starlette.Response` mentah dengan `content=token` (string) — BUKAN `JSONResponse`. Brief
pakai `r.json().get("token")`, yang akan melempar `JSONDecodeError` (subclass `ValueError`,
lolos ke `status_for`→`MUMBLE`, BUKAN error yang jelas). Dikoreksi jadi `token = r.text.strip()`.
Curl manual mengonfirmasi body persis token (`content-length` == panjang token, tidak ada
wrapping/whitespace):
```
HTTP/1.1 201 Created
content-length: 43

OdG0GIqqJzb7wPn9TnMpPfvNEvigJKVr1Oj67lX2Osg
```

Bagian LAIN dari brief (struktur `Checker(BaseChecker)`, `check()` cuma `GET /` dgn redirect
307→`/web/`→200 diikuti otomatis oleh `requests`, PUT/GET objek dgn header Basic manual,
`A.encode_state`/`A.decode_state`, exception handling `__main__` dgn `c` di luar `try`) dipakai
apa adanya — cocok dan tidak perlu diubah.

### Catatan tambahan yang TIDAK butuh perubahan kode (diverifikasi, aman)

- **"corrupt" (`flag_id` bogus) TIDAK boleh berupa JSON tak-valid** — itu akan membuat
  `A.decode_state` melempar `ValueError` → `status_for` → `MUMBLE` (103), BUKAN `CORRUPT` (102)
  yang diminta. Pola yang benar (sama seperti greple Task 2): JSON *valid* dengan nilai isi
  yang salah, mis. `{"u":"<user_asli>","t":"<token_asli>","n":"doesnotexist"}` — server balas
  `404` utk nama objek yang tak ada → `assert_eq(r.status_code, 200, ..., Status.CORRUPT)` di
  checker sudah menangani ini dgn benar tanpa perubahan.
- `A.rand_text(8).replace(" ", "")` (nama objek) secara teori bisa jadi string kosong kalau ke-8
  karakter acak semuanya spasi (peluang `(1/53)^8 ≈ 4×10⁻¹⁴`) — diputuskan tidak diubah, sama
  spt precedent greple (peluang diabaikan, konsisten dgn desain harness yg sudah ada).

---

## Detail arsitektur d3pl0y (utk konteks task berikutnya bila d3pl0y masuk roster resmi)

- **VM Hare TIDAK dipakai oleh jalur checker ini.** `config.EXECUTE_BINARY = "/app/vm"` hanya
  dipanggil oleh `internal.execute()`, yang cuma dipakai rute `POST /api/user/{owner}/{name}`
  (aksi "execute", body `{"argument":...,"suid":...}`) dan `POST /web/objects/execute`. Checker
  ini (register + PUT objek + GET objek) tidak pernah menyentuh binary VM. Build tetap sukses jadi
  ini cuma catatan arsitektur, bukan justifikasi workaround.
- **Reaper TTL 12 menit**: log startup menunjukkan proses background
  `d3pl0y-reaper` (`docker-entrypoint.sh` menjalankannya sebelum `exec gunicorn`) —
  `config.USER_TTL_SECONDS = 12*60`, sweep tiap `CLEANUP_INTERVAL_SECONDS = 60` detik. User (dan
  transitif object-nya) yang lebih tua dari 12 menit direaper. **Relevan utk tahap
  `config.enowars10.yml` nanti**: `round_time`/`flag_lifetime` sebaiknya jauh di bawah 12 menit,
  atau checker perlu registrasi user baru tiap PUT (yang memang sudah jadi desain checker ini —
  user baru per-PUT, bukan reuse). Tidak ada tindakan diambil sekarang (config sengaja ditunda).
- `config.MAX_OBJECT_BYTES = 1024` — flag ForcAD (puluhan byte) jauh di bawah batas ini, aman.

---

## Evidence gate (exact commands + output)

Server: `reky@192.168.43.136`. Service `d3pl0y` di HOST (bukan VM tim — pola sama dgn greple
Task 2: VM `10.13.37.x` waktu itu cuma sisa ~2.1GB, host+`forcad_default` lebih murah utk servis
HTTP ringan), network `forcad_default`, IP container `192.168.0.17:2553`.

Reachability check sebelum gate:
```
$ docker exec $C curl -m5 -s -o /dev/null -w "http_code=%{http_code}\n" 192.168.0.17:2553/
http_code=307
$ docker exec $C curl -m5 -s -o /dev/null -w "http_code=%{http_code}\n" -L 192.168.0.17:2553/
http_code=200
```

Deploy checker ke celery (host path langsung, `_lib` di-REUSE dari Task 2, TIDAK dibuat ulang):
```
~/adlab/forcad/checkers/_lib/adlab_eno.py                (sudah ada sejak Task 1/2, tidak diubah)
~/adlab/forcad/checkers/eno10_d3pl0y/checker.py          (baru, mode 755, owner reky:reky)
```
Diff vs repo lokal sebelum gate final: `diff_exit=0` (identik, tidak ada drift).

Gate run (persis versi checker.py yang di-commit):
```
$ C=$(docker ps -qf name=forcad-celery); IP=192.168.0.17
$ FLAG="ENOTESTFLAGd3pl0y7391826450AAAA="

$ docker exec $C /checkers/eno10_d3pl0y/checker.py check $IP; echo "check_exit=$?"
check_exit=101

$ docker exec $C /checkers/eno10_d3pl0y/checker.py put $IP "" "$FLAG" 0 > /tmp/d3_put.out 2>/tmp/d3_put.err
$ echo "put_exit=$?"
put_exit=101
$ cat /tmp/d3_put.out
{"u":"DeftCedar5533","t":"eqnTz9xPHFxU5-OozJz9sen0KiAFXIdt9yMH7aAHce4","n":"HfJgVeot"}

$ FID=$(cat /tmp/d3_put.out)
$ docker exec $C /checkers/eno10_d3pl0y/checker.py get $IP "$FID" "$FLAG" 0; echo "get_exit=$?"
get_exit=101

$ BOGUS='{"u":"DeftCedar5533","t":"eqnTz9xPHFxU5-OozJz9sen0KiAFXIdt9yMH7aAHce4","n":"doesnotexist"}'
$ docker exec $C /checkers/eno10_d3pl0y/checker.py get $IP "$BOGUS" "$FLAG" 0 >/tmp/d3_corrupt.out 2>/tmp/d3_corrupt.err
$ echo "corrupt_exit=$?"
corrupt_exit=102
$ cat /tmp/d3_corrupt.err
[__main__.Checker.get:52] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec $C /checkers/eno10_d3pl0y/checker.py check 10.13.37.99 >/tmp/d3_down.out 2>/tmp/d3_down.err
$ echo "down_exit=$?"
down_exit=104
$ cat /tmp/d3_down.err
ConnectionError(MaxRetryError("HTTPConnectionPool(host='10.13.37.99', port=2553): Max retries
exceeded with url: / (Caused by NewConnectionError('...Failed to establish a new connection:
[Errno 113] No route to host'))"))
```

Semua exit code sesuai yang diminta: **101 / 101 / 101 / 102 / 104**.

### Teardown (setelah gate lolos)
```
$ cd ~/adlab/eno10/d3pl0y && docker compose down -v
 Container d3pl0y-d3pl0y-1  Stopping/Stopped/Removing/Removed
teardown_exit=0

$ docker ps -a --format "{{.Names}}" | grep -i d3pl0y || echo "no d3pl0y containers"
no d3pl0y containers

$ docker network inspect forcad_default --format "{{range .Containers}}{{.Name}} {{end}}"
forcad-client-api-1 forcad-ticker-1 forcad-admin-api-1 forcad-events-1 forcad-redis-1
adlab-dashboard adlab-redis forcad-flower-1 forcad-postgres-1 adlab-eno-mongo forcad-celery-1
adlab-eno-shetcode forcad-http-receiver-1 forcad-rabbitmq-1 forcad-nginx-1
```
(15 anggota — sama dgn baseline semula, `d3pl0y` sudah tidak ada.)

Free memory server sebelum/sesudah teardown: available `6.1Gi` → `6.2Gi` (stabil, tidak ada
resource bocor).

---

## Bug infra ditemukan (BUKAN bug checker/service, TIDAK diperbaiki di repo — hanya dilaporkan)

`deploy/enowars10-deploy.sh` (dibuat Task 2) punya kerawanan laten di blok pembuatan
`docker-compose.override.yml`:

```bash
if [ ! -f "$OVERRIDE" ]; then
  {
    echo "services:"
    for s in $(docker compose config --services); do
      echo "  $s:"
      echo "    networks: [default, forcad_default]"
    done
    ...
  } > "$OVERRIDE"
fi
```

Pada percobaan pertama utk `d3pl0y`, `docker compose config --services` di dalam blok ini
mengembalikan STRING KOSONG (penyebab pastinya tidak berhasil direproduksi ulang — kemungkinan
kondisi transien terkait redirection `> "$OVERRIDE"` yang membuat shell membuat/truncate file
tujuan SEBELUM isi blok `{ }` dieksekusi, meski percobaan reproduksi manual dgn file kosong
tidak lagi memicu error yang sama). Yang PASTI & mekanis: begitu loop menghasilkan nol servis,
`docker-compose.override.yml` yang ditulis punya `services:` TANPA isi (null) → YAML tidak valid
utk compose ("services must be a mapping") → **dan karena skrip cuma membuat override kalau
belum ada, kegagalan ini PERMANEN sampai file dihapus manual** — retry apa pun akan terus gagal
identik.

**Workaround yang dipakai** (bukan fix ke skrip): hapus `docker-compose.override.yml` yang rusak,
tulis ulang MANUAL dengan format yang sudah terbukti jalan di greple:
```yaml
services:
  d3pl0y:
    networks:
      - forcad_default
networks:
  forcad_default:
    external: true
```
lalu `docker compose up -d --build` langsung (tidak lewat wrapper `enowars10-deploy.sh`).

**Tidak diperbaiki di `deploy/enowars10-deploy.sh`** karena (a) task ini eksplisit membatasi
commit HANYA ke `checker.py`, (b) akar penyebab pemicu awal (kenapa `--services` sempat kosong)
tidak berhasil direproduksi ulang scr meyakinkan sehingga fix yang tepat belum jelas (mis. apakah
cukup ganti idempotency-guard jadi validasi isi file, atau perlu restructure penulisan file spy
tidak lagi bergantung ke `>` di awal blok). **Rekomendasi utk task berikutnya yang memakai skrip
ini**: kalau ketemu error identik ("services must be a mapping" 2x setelah "dibuat
docker-compose.override.yml: services:" tanpa isi di bawahnya), langsung `rm
docker-compose.override.yml` lalu tulis manual spt di atas — jangan retry skrip apa adanya
(idempotency guard-nya akan membuatnya gagal permanen).

---

## File yang diubah/dibuat

- **`checkers/enowars10/d3pl0y/checker.py`** (baru, executable, 66 baris) — satu-satunya file
  yang di-commit, sesuai instruksi override task.
- **TIDAK diubah**: `deploy/enowars10-deploy.sh` (bug dilaporkan di atas, tidak dipatch — dipakai
  workaround manual di server saja), `forcad/config.enowars10.yml` (tidak dibuat/didaftarkan,
  registrasi ditunda sesuai instruksi eksplisit), `checkers/enowars10/_lib/*` (di-reuse apa
  adanya dari Task 1/2, tidak disentuh).

Sisi server (tidak dicommit, konsisten dgn pola checker lain — `eno_shetcode`, `faust_birthdaygram`,
`saar_licenser`, `eno10_greple`):
- `~/adlab/forcad/checkers/eno10_d3pl0y/checker.py` (dibiarkan terpasang di celery, sama spt
  `eno10_greple` masih ada di sana setelah Task 2 — ringan, tidak makan resource berarti).
- `~/adlab/eno10/d3pl0y/` (rsync source + `docker-compose.override.yml` tulisan tangan) —
  dipertahankan (tidak dihapus) utk rebuild berikutnya kalau masuk tahap roster; hanya
  CONTAINER-nya yang di-teardown. Berbeda dgn greple, TIDAK ada patch Dockerfile/source di sini
  (build sukses tanpa modifikasi apa pun).

---

## Self-review

- **Faithfulness ke brief**: struktur `Checker(BaseChecker)`, method `check/put/get`, exception
  handling `__main__` (Checker construction DI LUAR try, sudah sesuai fix Task 2) dipakai
  verbatim. Deviasi HANYA pada 3 hal request-shape (prefix `/api`, form vs json, teks vs JSON
  respons) — semua diverifikasi baca source ASLI (`api.py`/`app.py`) DAN curl manual dari vantage
  point yang sama dgn gate (dalam container celery), bukan tebakan.
- **Tidak ada state palsu**: setiap exit code & output di atas adalah hasil run asli yang barusan
  dieksekusi berurutan dlm satu sesi (tidak ada run terpisah yg hasilnya diasumsikan sama), termasuk
  diff eksplisit checker.py lokal vs server SEBELUM gate final utk memastikan tidak ada drift.
- **Isolasi perubahan**: tidak ada file service (`d3pl0y/Dockerfile`, `vm/*.ha`, dst.) yang disentuh
  sama sekali — baik di laptop maupun salinan server — karena build sukses tanpa perlu patch.
  Dicek `git status` di laptop utk source d3pl0y bukan bagian dari repo yg dipantau (itu repo
  bank-soal terpisah), tapi tidak ada operasi write ke path tsb setelah rsync awal.
- **Commit bersih**: `git add` eksplisit 1 file (`checkers/enowars10/d3pl0y/checker.py`), dicek
  `git status --porcelain` sebelum & sesudah commit — hanya file itu yang ter-stage, `.omc/`
  (punya orkestrator, sudah ada sejak awal sesi) tidak ikut.
- **Resource server**: `d3pl0y` di-teardown penuh (`docker compose down -v`), network attachment
  hilang, memory available server kembali ke baseline (~6.2Gi), tidak ada container/volume nyisa.
- **Kekhawatiran kecil (bukan blocker)**: bug `deploy/enowars10-deploy.sh` di atas (override
  self-poisoning) belum diperbaiki di repo — task berikutnya yang memakai skrip ini utk servis
  BARU (bukan d3pl0y/greple yang override-nya sudah benar) berisiko kena masalah yang sama kalau
  `docker compose config --services` kebetulan gagal sesaat pada percobaan pertama. Sudah
  didokumentasikan di atas dgn workaround yang jelas.
