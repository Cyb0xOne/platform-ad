# Task 5 Report: Checker `signmemaybe` (:1984) — contracts, X-Session-Token

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(flag_id bogus)=102`, `check(host mati)=104`.
Commit: `66779c6` — `feat(eno10): checker signmemaybe (contracts) + gate lolos` (branch
`enowars10-checkers`).

Servis .NET 10 ini **build mulus tanpa patch Dockerfile** (beda dari greple/flagdrive yang
masing-masing butuh 2 patch) — satu-satunya hambatan infra adalah bug `deploy/
enowars10-deploy.sh` yang sudah diparkir sejak Task 3 (lihat bawah), yang kali ini benar-benar
kejadian (bukan cuma risiko teoretis).

---

## Ringkasan alur

1. Baca brief + baca ULANG source asli nyata (`AuthEndpoints.cs`, `ContractEndpoints.cs`,
   `Requests.cs`, `AuthService.cs`, `Hashing.cs`, `RootEndpoints.cs`, `Program.cs`,
   `Database.cs`, `AnnexDirectiveParser.cs`, `RemoteAnnexFetcher.cs`) sebelum menulis checker —
   brief eksplisit bilang 4 task sebelumnya semua meleset di titik berbeda.
2. Tulis `checkers/enowars10/signmemaybe/checker.py` dari template brief + koreksi (lihat bawah).
3. rsync source `SignMeMaybe/` dari laptop ke server (`~/adlab/eno10/signmemaybe/`, exclude
   `data.stale/`, `bin/`, `obj/`).
4. `~/adlab/enowars10-deploy.sh signmemaybe up` **kena bug parkir Task 3**: `docker compose
   config --services` balas kosong di percobaan pertama → skrip menulis
   `docker-compose.override.yml` rusak (`services:` mapping null) → SEMUA panggilan `docker
   compose` berikutnya gagal `"services must be a mapping"` (chicken-and-egg, bahkan `--services`
   sendiri ikut gagal). Diperbaiki PERSIS sesuai instruksi brief: hapus override, konfirmasi
   `docker compose config --services` bersih (`signmemaybe`, `signmemaybe-cleanup`), tulis
   tangan override yang benar (lihat diff di bawah). Skrip **tidak disentuh** (di luar scope).
5. Build .NET (`docker compose up -d --build`) dijalankan `nohup` di background, di-poll via
   Monitor tool (bukan menunggu blocking) — selesai ~6 menit, sukses tanpa patch build apa pun.
6. Reachability + verifikasi bentuk request MANUAL via curl dari DALAM container celery (vantage
   point sama dgn gate) SEBELUM menjalankan checker resmi: `/api/info`, `/health`, register,
   login, buat kontrak, ambil kontrak by reference, kontrak nonexistent (404), tanpa token (401)
   — semua dicocokkan ke `checker.py` sebelum gate resmi.
7. Deploy checker ke celery (host path langsung `~/adlab/forcad/checkers/eno10_signmemaybe/
   checker.py`, mode 755), diff eksplisit vs repo lokal (identik), sanity-import di dalam
   container sebagai user `nobody`.
8. Gate 5-langkah — semua lolos exit code yang diminta.
9. Teardown (`docker compose down -v`), verifikasi container hilang, `forcad_default` balik ke
   15 anggota, memory available balik ke/atas baseline.
10. Commit HANYA `checkers/enowars10/signmemaybe/checker.py`. `forcad/config.enowars10.yml`
    TIDAK disentuh, TIDAK ada ronde engine dijalankan (sesuai instruksi override task).

---

## Perubahan bentuk request terhadap brief

Brief benar untuk prefix rute dasar (`/api/register`, `/api/login`), nama field body masuk
(`username`/`password`, `title`/`content`), dan nama header (`X-Session-Token`). **Deviasi kritis
ada di respons `POST /api/contracts` dan di rute baca kontrak** — brief menebak bentuk REST
generik (`{id}` di body & di URL) yang ternyata tidak ada sama sekali di implementasi nyata.

### 1. KRITIS — `POST /api/contracts` tidak pernah mengembalikan field `id`

`src/Endpoints/ContractEndpoints.cs:173-182` (`CreateContract`, balasan sukses):
```csharp
return Results.Created($"/api/contracts/{Uri.EscapeDataString(reference)}/versions/latest", new
{
    reference,
    ownerUsername = user.Username,
    title,
    versionNumber = 1,
    approvalState = "draft",
    checksum,
    archiveTicket
});
```
Tidak ada properti `id` di anonymous object ini sama sekali — id numerik internal (`contractId`,
kolom `contracts.id` di `src/Data/Database.cs:53`) **tidak pernah diekspos ke klien**. Pengenal
publik kontrak adalah `reference` (string `"CNTR-<24 hex>"`, dibuat di
`Database.CreateContractReference():449-452` atau `ContractEndpoints.CreateArchiveReference():
674-692`). Brief's `r.json().get("id")` akan selalu `None` → `assert_(cid is not None, ...)`
GAGAL di setiap `put()` → checker tidak akan pernah lolos gate dengan kode brief apa adanya.

**Dikonfirmasi empiris via curl manual** (container celery, token user baru):
```
$ curl -X POST http://192.168.0.17:1984/api/contracts -H "X-Session-Token: $TOK" \
    -d '{"title":"curl test title","content":"ENOTESTFLAGcurlmanualverify1234AAAA="}'
{"reference":"CNTR-19be02988586b09107db05ef","ownerUsername":"curltestuser_7",
 "title":"curl test title","versionNumber":1,"approvalState":"draft",
 "checksum":"68b983e2...","archiveTicket":null}   http_code=201
```
Koreksi: `put()` mengambil `r.json().get("reference")`, disimpan di state sbg `r`.

### 2. KRITIS — tidak ada rute `GET /api/contracts/{id}` generik

`src/Endpoints/ContractEndpoints.cs:17-41` (`MapContractEndpoints`) hanya mendaftarkan:
- `GET /api/contracts` (list) — **milik SENDIRI saja** (filter `WHERE c.owner_user_id =
  $owner_user_id`, baris 359), dan tiap entry list TIDAK punya field `content` (cuma
  `checksum`/`versionNumber`/dst, lihat baris 374-387) — tidak bisa dipakai `get()`.
- `GET /api/contracts/{reference}/versions/latest` (baris 34-35) — **inilah** rute baca isi
  penuh (`GetLatestContractVersion`, baris 531-590), balasannya:
  ```csharp
  return Results.Ok(new {
      reference = reader.GetString(0), ownerUsername = reader.GetString(1),
      title = reader.GetString(2), versionNumber = reader.GetInt32(3),
      approvalState = reader.GetString(4), checksum = reader.GetString(6),
      createdAt = reader.GetString(8), requestedByUsername = user.Username,
      content, pdfUrl = $"/api/contracts/{Uri.EscapeDataString(reference)}/versions/latest/pdf"
  });
  ```
  Field `content` (baris 575: `var content = reader.GetString(7)` dari kolom
  `contract_versions.content_text`) **disalin verbatim** dari `request.Content` saat `PUT`
  (baris 166: `Database.AddParameter(insertVersion, "$content_text", request.Content)`) — bukan
  echo dari request GET, jadi aman dipakai sbg bukti flag benar-benar tersimpan di DB.
  Otorisasi endpoint ini HANYA `AuthService.TryGetUser` (baris 538: sesi valid APAPUN, bukan
  dicek kepemilikan) — kemungkinan besar ini vuln yang dimaksud (reference jadi bearer-token
  de-facto), tapi di luar scope checker.

**Dikonfirmasi empiris**:
```
$ curl http://192.168.0.17:1984/api/contracts/CNTR-19be02988586b09107db05ef/versions/latest \
    -H "X-Session-Token: $TOK"
{"reference":"CNTR-19be...","...","content":"ENOTESTFLAGcurlmanualverify1234AAAA=",
 "pdfUrl":"/api/contracts/.../pdf"}   http_code=200

$ curl http://192.168.0.17:1984/api/contracts/CNTR-000000000000000000000000/versions/latest \
    -H "X-Session-Token: $TOK"
{"error":"contract not found"}   http_code=404
```
Koreksi: `get()` memanggil `GET /api/contracts/{r}/versions/latest`, memeriksa
`r.json().get("content", "")` (bukan `r.text` mentah — supaya tak kebetulan cocok field lain
mis. `pdfUrl` yang juga memuat substring `reference`).

### 3. Verifikasi tambahan (bukan koreksi, BENAR dari awal di brief)

- **Header** `X-Session-Token` — persis (`AuthService.cs:52`,
  `request.Headers.TryGetValue("X-Session-Token", ...)`).
- **Body register/login** `{username,password}` — persis (`Models/Requests.cs:3-5`; JSON
  camelCase policy di `Program.cs:51` tak mengubah nama krn sudah lowercase-first).
- **Field token** balasan login `token` — persis (`AuthEndpoints.cs:104-109`,
  `AuthService.CreateSession`). Dikonfirmasi curl: `{"userId":1,"username":"...","token":"..."}`
  http 200 (BUKAN 201 — catatan kecil, tak berdampak krn checker cuma cek `//100==2`).
- **Body buat kontrak** `{title,content}` — persis (`Models/Requests.cs:7`,
  `ContractCreateRequest(string Title, string Content, string? ArchivePacket = null)`).

Semua di atas dikonfirmasi ganda: baca source DAN curl manual dari dalam celery sebelum menulis
gate resmi.

### 4. Endpoint `check()` — tak disebutkan eksplisit di brief, dipilih dari source

Brief tak menentukan endpoint utk `check()` (kontrak recon §3 cuma sebut register/login/
contracts). Dipilih `GET /api/info` (`RootEndpoints.cs:9-14`, tanpa auth, balas JSON
`{service,message,status}` — dikonfirmasi curl: `{"service":"SignMeMaybe","message":
"Departmental contract registry.","status":"online"}` http 200) drpd `GET /` (Razor Index, butuh
`wwwroot` statis + `UseStaticFiles()` — lebih rapuh sbg basis assert). `check()` memvalidasi
`status_code==200` DAN `json()["status"]=="online"` (dua assert terpisah, MUMBLE kalau salah
satu gagal) — bukan cuma status code mentah spt template brief.

---

## Detail arsitektur signmemaybe (konteks utk task berikutnya bila masuk roster resmi)

- **Reaper 720 detik**: `SIGNMEMAYBE_CLEANUP_RETENTION_SECONDS=720` (`docker-compose.yml:28`,
  default sama di `ServiceOptions.cs:34` bila env tak diset) — dijalankan oleh container
  `signmemaybe-cleanup` terpisah (cron, `Dockerfile.cleanup` + `cleanup/cleanup-crontab`), BUKAN
  proses in-process spt d3pl0y/flagdrive. Menguatkan catatan lintas-task yg sudah ada di
  `progress.md` (Task 3/4): `round_time × flag_lifetime` sebaiknya jauh di bawah ~720 detik kalau
  `signmemaybe` ikut diregistrasi ke `config.enowars10.yml` nanti. User baru per-`put()` (desain
  checker ini) menghindari masalah reaper utk PUT/GET jarak dekat, tapi bukan jaminan mutlak kalau
  round_time besar.
- **`checker_timeout` brief = 25** — dicatat verbatim utk dipakai saat registrasi config nanti
  (langkah itu sengaja ditunda, lihat bawah).
- **`AnnexDirectiveParser`/`RemoteAnnexFetcher`** (`src/Documents/`): kontrak yang isinya
  mengandung tag literal `<link rel="attachment" href="...">` memicu SSRF-terbatas (server
  fetch URL tsb, embed ke PDF sbg attachment, dgn allow-list ketat: bukan alamat privat/loopback
  kecuali redirect balik ke endpoint internal `/internal/archive/packets/{ticket}` miliknya
  sendiri). Diperiksa regex-nya (`LinkTagPattern`) — flag acak dari ForcAD (alnum/base64-ish)
  tidak mungkin kebetulan cocok pola ini, jadi **tidak ada risiko hang/timeout** di `put()` dari
  konten flag itu sendiri. Tidak dieksploitasi maupun disentuh checker — dicatat murni sbg
  observasi arsitektur (kemungkinan ini vuln utama servis, bareng dgn kurangnya cek kepemilikan
  di `GetLatestContractVersion`).
- **Otorisasi `GET .../versions/latest` tidak mengecek kepemilikan** (`AuthService.TryGetUser`
  saja, `ContractEndpoints.cs:538`) — sesi user MANAPUN bisa baca kontrak MANAPUN asalkan tahu
  `reference`-nya. Checker sengaja tetap pakai token+reference milik sendiri (state), tidak
  mengandalkan celah ini — tapi dicatat krn kemungkinan besar ini "vuln" yang dimaksud desain
  servis.
- **Password hashing**: PBKDF2-SHA256 asli (`Security/Hashing.cs`, 20000 iterasi default,
  bukan plaintext/hash lemah spt beberapa servis sebelumnya) — tak ada dampak ke checker.

---

## Bug infra ditemukan & diperbaiki — `docker-compose.override.yml` (SALINAN SERVER SAJA)

Sesuai catatan "Parked finding" di brief (sudah didiagnosis sejak Task 3, kali ini benar-benar
kejadian): `deploy/enowars10-deploy.sh` menulis override HANYA kalau file belum ada, dengan isi
diturunkan dari `docker compose config --services`. Pada percobaan pertama di
`~/adlab/eno10/signmemaybe/`, perintah itu balas KOSONG (sebab tak jelas — retry tanpa perubahan
kode apa pun langsung berhasil; kemungkinan besar cold-start compose/plugin warm-up, bukan isu
struktural pada `docker-compose.yml` servis yang memang valid), sehingga skrip menulis:

```yaml
# --- SEBELUM (rusak, dihasilkan skrip) ---
services:
networks:
  default: {}
  forcad_default:
    external: true
```

`services:` dgn value kosong = `null` di YAML → `docker compose` MANA PUN (termasuk
`--services` sendiri) gagal fatal: `"services must be a mapping"` — chicken-and-egg permanen
persis spt diprediksi brief (skrip TIDAK self-heal krn guard "hanya tulis kalau belum ada" jadi
menghalangi perbaikan otomatis di run berikutnya).

**Fix** (dieksekusi sesuai instruksi eksplisit brief — hapus & tulis tangan, TIDAK menyentuh
skrip):
```bash
$ rm -f docker-compose.override.yml
$ docker compose config --services      # kini bersih (masalahnya transient)
signmemaybe
signmemaybe-cleanup
```
```yaml
# --- SESUDAH (tulisan tangan) ---
services:
  signmemaybe:
    networks: [default, forcad_default]
  signmemaybe-cleanup:
    networks: [default, forcad_default]
networks:
  default: {}
  forcad_default:
    external: true
```
Divalidasi (`docker compose config --services` balas kedua nama bersih) sebelum `docker compose
up -d --build` dijalankan. Build sesudahnya sukses penuh tanpa patch Dockerfile apa pun — beda
dari greple (2 patch Zig) dan flagdrive (2 patch: BuildKit cache-mount + href tailwind) yang
keduanya diperlukan SEBELUM build pertama bisa jalan sama sekali. `Dockerfile` &
`Dockerfile.cleanup` signmemaybe dicek eksplisit (`grep -n "mount=type=cache"` nihil di
keduanya) — tak ada blok `RUN --mount=type=cache` sama sekali, jadi isu BuildKit yg melanda
greple/flagdrive TIDAK relevan di sini.

`deploy/enowars10-deploy.sh` sendiri **tidak diubah** (di luar scope, sesuai instruksi brief).

---

## Evidence gate (exact commands + output)

Server: `reky@192.168.43.136`. Service `signmemaybe` di HOST (bukan VM tim), network
`forcad_default`, IP container `192.168.0.17:1984`.

### Build
```
$ cd ~/adlab/eno10/signmemaybe && docker compose up -d --build   # (setelah override diperbaiki)
...
 Image signmemaybe_service-signmemaybe Building
 Container signmemaybe_service-signmemaybe-1 Started
 Container signmemaybe_service-signmemaybe-cleanup-1 Started
BUILD_SUCCESS (di-poll via Monitor tool ber-background, ~6 menit elapsed, tanpa blocking)
```

### Reachability + verifikasi manual (dari dalam celery, SEBELUM gate resmi)
```
$ C=$(docker ps -qf name=forcad-celery); IP=192.168.0.17

$ docker exec $C curl -m5 http://$IP:1984/api/info
{"service":"SignMeMaybe","message":"Departmental contract registry.","status":"online"} http_code=200

$ docker exec $C curl -m5 http://$IP:1984/health
{"status":"ok","service":"SignMeMaybe"}   http_code=200

$ docker exec $C curl -X POST http://$IP:1984/api/register -d '{"username":"curltestuser_7","password":"curltestpass12345"}'
{"userId":1,"username":"curltestuser_7","token":"6c437b15..."}   http_code=200

$ docker exec $C curl -X POST http://$IP:1984/api/login -d '{"username":"curltestuser_7","password":"curltestpass12345"}'
{"userId":1,"username":"curltestuser_7","token":"c7c91746..."}   http_code=200

$ docker exec $C curl -X POST http://$IP:1984/api/contracts -H "X-Session-Token: c7c91746..." \
    -d '{"title":"curl test title","content":"ENOTESTFLAGcurlmanualverify1234AAAA="}'
{"reference":"CNTR-19be02988586b09107db05ef","ownerUsername":"curltestuser_7","title":"curl test title",
 "versionNumber":1,"approvalState":"draft","checksum":"68b983e2...","archiveTicket":null}   http_code=201

$ docker exec $C curl http://$IP:1984/api/contracts/CNTR-19be02988586b09107db05ef/versions/latest \
    -H "X-Session-Token: c7c91746..."
{"reference":"CNTR-19be...","...","content":"ENOTESTFLAGcurlmanualverify1234AAAA=","pdfUrl":"..."}  http_code=200

$ docker exec $C curl http://$IP:1984/api/contracts/CNTR-000000000000000000000000/versions/latest \
    -H "X-Session-Token: c7c91746..."
{"error":"contract not found"}   http_code=404

$ docker exec $C curl http://$IP:1984/api/contracts/CNTR-19be.../versions/latest   # tanpa header
(empty body)   http_code=401
```

### Deploy checker
```
~/adlab/forcad/checkers/_lib/adlab_eno.py                 (sudah ada, TIDAK diubah)
~/adlab/forcad/checkers/eno10_signmemaybe/checker.py       (baru, mode 755, owner reky:reky)
```
Diff vs repo lokal sebelum gate final: `diff_exit=0` (identik — diverifikasi ulang via scp +
diff setelah gate, hasil sama). Sanity-import di dalam container sbg user `nobody`:
`python3 -c "import checker"` (sys.path diarahkan manual ke `/checkers/eno10_signmemaybe` +
`/checkers/_lib`) → `import OK 1984`, tanpa error.

### Gate run (persis versi checker.py yang di-commit)
```
$ C=$(docker ps -qf name=forcad-celery); IP=192.168.0.17

$ docker exec $C /checkers/eno10_signmemaybe/checker.py check $IP; echo "check_exit=$?"
check_exit=101

$ FLAG="ENOTESTFLAGsignmemaybe9284736501WXYZ="
$ docker exec $C /checkers/eno10_signmemaybe/checker.py put $IP "" "$FLAG" 0 >/tmp/smm_put.out 2>/tmp/smm_put.err
$ echo "put_exit=$?"
put_exit=101
$ cat /tmp/smm_put.out
{"t":"5684073c10fa86406fa1121067fff631f8044d64aa5dc940aef18b6cea0f2524","r":"CNTR-60b57665e4ee2dbf9309e45e"}

$ FID=$(cat /tmp/smm_put.out)
$ docker exec $C /checkers/eno10_signmemaybe/checker.py get $IP "$FID" "$FLAG" 0; echo "get_exit=$?"
get_exit=101

$ BOGUS='{"t":"5684073c10fa86406fa1121067fff631f8044d64aa5dc940aef18b6cea0f2524","r":"CNTR-000000000000000000000000"}'
$ docker exec $C /checkers/eno10_signmemaybe/checker.py get $IP "$BOGUS" "$FLAG" 0 >/tmp/smm_corrupt.out 2>/tmp/smm_corrupt.err
$ echo "corrupt_exit=$?"
corrupt_exit=102
$ cat /tmp/smm_corrupt.err
kontrak tak terambil
[__main__.Checker.get:55] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec $C /checkers/eno10_signmemaybe/checker.py check 10.13.37.99 >/tmp/smm_down.out 2>/tmp/smm_down.err
$ echo "down_exit=$?"
down_exit=104
$ cat /tmp/smm_down.err
checker error
ConnectionError(MaxRetryError("HTTPConnectionPool(host='10.13.37.99', port=1984): Max retries
exceeded with url: /api/info (Caused by NewConnectionError('...Failed to establish a new
connection: [Errno 113] No route to host'))"))
```

Semua exit code sesuai yang diminta: **101 / 101 / 101 / 102 / 104**.

Catatan mekanisme "bogus flag_id" (sama seperti Task 3/4): bogus HARUS berupa JSON *valid* dgn
isi salah (di sini: token asli + `reference="CNTR-000000000000000000000000"` yg nonexistent,
dikonfirmasi 404 lewat curl manual di atas), BUKAN string bukan-JSON — kalau bukan-JSON,
`A.decode_state` melempar `ValueError` yg lolos ke `except Exception as e: cquit(A.status_for(e),
...)` di `__main__`, dan `status_for` memetakan `ValueError` → `MUMBLE` (103), BUKAN `CORRUPT`
(102) yg diminta.

### Teardown (setelah gate lolos)
```
$ cd ~/adlab/eno10/signmemaybe && docker compose down -v
 Container signmemaybe_service-signmemaybe-cleanup-1 Removed
 Container signmemaybe_service-signmemaybe-1 Removed
 Network signmemaybe_service_default Removed
teardown_exit=0

$ docker ps -a --format "{{.Names}}" | grep -i signmemaybe || echo "no signmemaybe containers"
no signmemaybe containers

$ docker network inspect forcad_default --format "{{range .Containers}}{{.Name}} {{end}}"
forcad-client-api-1 forcad-ticker-1 forcad-admin-api-1 forcad-events-1 forcad-redis-1
adlab-dashboard adlab-redis forcad-flower-1 forcad-postgres-1 adlab-eno-mongo forcad-celery-1
adlab-eno-shetcode forcad-http-receiver-1 forcad-rabbitmq-1 forcad-nginx-1
```
(15 anggota — sama dgn baseline. Memory available: `6.3Gi` (baseline sblm build, saat image
pull mulai) → `6.4Gi` (sesudah teardown) — stabil, tidak ada resource bocor. Tidak ada named
Docker volume utk `signmemaybe` (compose-nya cuma bind-mount `./data/:/data:rw`, beda dari
d3pl0y/flagdrive yg pakai named volume Postgres) — `down -v` tak mencetak baris "Volume Removed"
krn memang tak ada yg perlu dihapus; sisa `~/adlab/eno10/signmemaybe/data/*.sqlite3` di host
sengaja dibiarkan, konsisten dgn precedent flagdrive [menyimpan salinan server utk rebuild
berikutnya]).

---

## File yang diubah/dibuat

- **`checkers/enowars10/signmemaybe/checker.py`** (baru, executable, 72 baris) — satu-satunya
  file yang di-commit, sesuai instruksi override task.
- **TIDAK diubah**: `deploy/enowars10-deploy.sh`, `forcad/config.enowars10.yml` (registrasi
  ditunda, sesuai instruksi eksplisit), `checkers/enowars10/_lib/*` (di-reuse apa adanya),
  `checkers/requirements.txt` server & `docker_config/celery/Dockerfile.fast` (tidak perlu dep
  baru — checker hanya pakai stdlib `sys`/`pathlib` + `checklib`/`requests`/`adlab_eno` yg sudah
  ada; tidak disentuh sesuai konstrain).

Sisi server (tidak dicommit, konsisten dgn pola checker lain):
- `~/adlab/forcad/checkers/eno10_signmemaybe/checker.py` (dibiarkan terpasang di celery).
- `~/adlab/eno10/signmemaybe/` — rsync source + `docker-compose.override.yml` tulisan tangan
  (dipertahankan, TIDAK dihapus, utk rebuild berikutnya kalau masuk tahap roster) + data sqlite
  bind-mount sisa. Tidak ada patch `Dockerfile`/`Dockerfile.cleanup` yg perlu dipertahankan (tak
  ada yg dibutuhkan sama sekali).
- Laptop source (`~/workspaces/cylab/ctf/.../SignMeMaybe/`) — **tidak disentuh sama sekali**,
  dicek tidak ada operasi write ke path tsb setelah rsync awal (hanya `Read` tool dipakai utk
  membaca source).

---

## Self-review

- **Faithfulness ke brief**: struktur `Checker(BaseChecker)`, method `check/put/get`, exception
  handling `__main__` (Checker construction DI LUAR try) dipakai verbatim. Header
  `X-Session-Token`, body register/login/contracts SEMUA benar sesuai brief (dikonfirmasi baca
  source + curl) — deviasi HANYA pada bentuk RESPONS `POST /api/contracts` (field `reference`
  bukan `id`) dan RUTE baca kontrak (`.../versions/latest`, bukan `/api/contracts/{id}`
  generik). Keduanya dikonfirmasi empiris via curl manual SEBELUM ditulis ke checker resmi,
  bukan tebakan, dan lolos gate LIVE dgn kredensial yg BEDA dari verifikasi manual (lihat FLAG
  di evidence gate vs `ENOTESTFLAGcurlmanualverify...` di verifikasi manual).
- **Tidak ada state palsu**: setiap exit code & output di atas hasil run asli berurutan dlm satu
  sesi; token/reference di evidence gate BERBEDA dari token/reference di verifikasi manual curl
  (buktinya checker resmi benar-benar dieksekusi ulang dgn kredensial baru, bukan reuse data
  curl manual sebelumnya).
- **Klasifikasi status disengaja per-kasus**: `check()`/`put()` pakai `Status.MUMBLE` utk semua
  kegagalan langkah (register/login/buat-kontrak gagal = servis "hidup tapi salah", bukan flag
  hilang) sesuai definisi task; `get()` pakai `Status.CORRUPT` utk status code bukan-200 ATAU
  flag tak ketemu di `content` (keduanya berarti "flag sudah tak bisa diambil lagi", sesuai
  definisi CORRUPT). Fallback `status_for()` di `__main__` menangani DOWN (koneksi) & MUMBLE
  (ValueError/KeyError/dst) di luar assert eksplisit.
- **Isolasi perubahan**: TIDAK ada patch Dockerfile/source servis yg perlu dipertahankan (build
  mulus dari awal setelah override compose diperbaiki); laptop source (bank-soal repo terpisah)
  tidak tersentuh, dicek tidak ada operasi write ke path tsb.
- **Commit bersih**: `git add` eksplisit 1 file, `git status --porcelain` dicek sebelum & sesudah
  commit — hanya `checkers/enowars10/signmemaybe/checker.py` ter-stage (`.omc/` sudah ada sejak
  awal sesi, tidak ikut).
- **Resource server**: `signmemaybe` di-teardown penuh (`docker compose down -v`), network
  attachment hilang, memory available server balik ke/di atas baseline, tidak ada
  container/volume nyisa. Baseline diambil SEBELUM containers hidup (saat image pull baru mulai)
  sengaja, utk perbandingan yg fair.

## Kekhawatiran (bukan blocker)

- Sama seperti catatan Task 3/4: `assert_eq(r.status_code, 200, ..., Status.CORRUPT)` di `get()`
  menyamaratakan SEMUA non-200 (401 tanpa/invalid token, 404 reference salah, 5xx transien) jadi
  CORRUPT — 5xx transien secara prinsip lebih tepat MUMBLE. Preseden identik di
  greple/d3pl0y/flagdrive, sengaja dibiarkan konsisten (kalau mau diperbaiki, sebaiknya
  sekaligus di keempatnya, bukan hanya signmemaybe).
- **Vuln arsitektur dicatat, tidak dieksploitasi**: `GET /api/contracts/{reference}/versions/
  latest` tidak mengecek kepemilikan (`ContractEndpoints.cs:538`, `AuthService.TryGetUser` sesi
  APAPUN) — kemungkinan besar ini "vuln" resmi servis (reference jadi bearer-token de-facto,
  mungkin dikombinasi dgn kebocoran reference lewat `AnnexDirectiveParser`/PDF). Checker sengaja
  tidak bergantung pada celah ini (pakai token+reference milik sendiri), jadi tidak berisiko
  false-negative kalau celah ini di-patch tim lain saat attack-defense berjalan.
  `SigningEndpoints.cs` (EC signing authorities/ceremonies) juga tidak dibaca detail —
  di luar scope checker kontrak, dicatat sbg permukaan lain yg belum diperiksa.
- Reaper 720 detik (`SIGNMEMAYBE_CLEANUP_RETENTION_SECONDS`, dijalankan via cron container
  terpisah `signmemaybe-cleanup`, BUKAN in-process spt d3pl0y/flagdrive) — relevan utk keputusan
  `round_time`/`flag_lifetime` di `config.enowars10.yml` nanti (belum jadi masalah sekarang krn
  config ditunda & checker registrasi user baru tiap PUT). `checker_timeout: 25` dari brief
  dicatat verbatim utk dipakai saat itu.
- `rand_username()`/`rand_password()` (dari `adlab_eno`, dipakai apa adanya, tak diubah) —
  risiko kolisi username teoretis sama spt task-task sebelumnya (register balas 409, assert
  `//100==2` MUMBLE dgn benar, bukan crash) — tidak diubah, konsisten dgn precedent.
- Penyebab asli `docker compose config --services` balas kosong di percobaan pertama TIDAK
  terdiagnosis tuntas (retry langsung berhasil tanpa perubahan apa pun) — kemungkinan cold-start
  Docker Compose plugin v5.1.2 di server ini, bukan masalah struktural pada
  `docker-compose.yml`/`.env` signmemaybe (keduanya valid, dikonfirmasi `docker compose config
  --services` bersih sesudahnya). Kalau task berikutnya mengalami hal sama, workaround yg sudah
  terbukti: hapus override rusak → retry `--services` → tulis tangan override yg benar.
