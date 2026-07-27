# Task 2 Report: Checker `greple` (:7777) — template HTTP

## Status: DONE

Gate lolos penuh: `check=101 put=101 get=101`, `get(pid bogus)=102`, `check(host mati)=104`.
Commit: `bd9ea4b` — `feat(eno10): checker greple (pastebin) + deploy helper, gate lolos` (branch `enowars10-checkers`).

---

## Ringkasan alur

1. rsync source `greple/` dari laptop ke server (`~/adlab/eno10/greple/`).
2. Build gagal 2x karena masalah SERVICE (bukan checker) — diperbaiki dengan patch mekanis kecil di salinan server. Lihat "Masalah build" di bawah.
3. Deploy greple di HOST server, ditempel ke network `forcad_default` (bukan VM tim — VM `10.13.37.11/.12` cuma sisa ~2.1GB available dgn 7 container tiap satu, sedangkan host punya 6.2GB available; host+forcad_default juga menghindari risiko nftables/nested-network dan lebih murah untuk servis HTTP ringan).
4. Curl manual ke `/`, `/pastebin`, `/p/{hex}` untuk pelajari bentuk request/response NYATA (recon §7 di spec cuma menyebut kontrak garis besar, bukan nama field body persis).
5. Tulis `checker.py` dari template brief, dikoreksi 2 hal berdasar respons nyata (lihat bawah).
6. Deploy ke container `forcad-celery` — nemu bug jalur `_lib` di brief Step 3 (lihat "Bug ditemukan").
7. Gate check/put/get + corrupt + down — semua lolos dgn exit code yang diharapkan.
8. Commit `checker.py` + `deploy/enowars10-deploy.sh` (TIDAK menyentuh `forcad/config.enowars10.yml`, sesuai instruksi override).
9. Teardown greple (`docker compose down -v`), konfirmasi container hilang dan network `forcad_default` balik ke anggota semula.

---

## Perubahan bentuk request terhadap brief (dan alasannya)

Brief Step 1 memberi checker.py sebagai starting point yang eksplisit disebut "iterasi terhadap respons nyata". Setelah curl manual ke greple yang benar-benar jalan, 2 hal di brief ternyata salah:

### 1. Field body pastebin: `title`+`text`, bukan `content`

Source `src/main.zig` fungsi `postPastebin`:
```zig
const title = try req.getParamStr(alloc, "title") orelse return error.InvalidRequest;
const text = try req.getParamStr(alloc, "text") orelse return error.InvalidRequest;
```
Brief memakai `data={"content": flag}` — field `content` tidak ada sama sekali, jadi `text` (dan `title`, wajib ada) tidak terisi, dan server balas `error.InvalidRequest` (400). Diganti jadi:
```python
data={"title": A.rand_text(12), "text": flag}
```

### 2. ID paste ada di header `Location` (redirect 302), bukan di body 2xx

Brief mengasumsikan `assert_eq(r.status_code // 100, 2, ...)` lalu cari hex id di `r.text`. Respons nyata (dicek via curl `-D -` tanpa follow-redirect):
```
HTTP/1.1 302 Found
Location:/p/381d43e5ff625d86f4d01f40d256b366d5d0623dd790066aafa443c8
content-length:5
```
Body-nya cuma teks `moved` — TIDAK ada hex id di body sama sekali. `postPastebin` di source memang `req.redirectTo(location, null)`, bukan balas 2xx. Checker diubah untuk:
- expect `r.status_code == 302` (bukan `//100==2`),
- pakai `allow_redirects=False` supaya deterministik (bukan bergantung ke default-follow `requests`),
- ambil id dari `r.headers.get("Location")`, bukan `r.text`.

### 3. Panjang hex id dikunci 56 karakter

`utils.Hash = [HashFn.digest_length]u8` dengan `HashFn = std.crypto.hash.sha2.Sha224` → 28 byte → 56 hex char. Rute `GET /p/{hex}` di `main.zig` mensyaratkan `path.len == 3 + @sizeOf(utils.Hash) * 2` PERSIS — id yang lebih pendek/panjang tidak match rute paste sama sekali dan jatuh ke 404 generik. Regex brief (`[0-9a-f]+` atau fallback `{8,}`) sebetulnya bisa saja masih match karena greedy, tapi dikunci eksplisit `{56}` supaya jelas & tak salah tangkap substring lain. Ini juga alasan test "corrupt" (`pid=deadbeef`, 8 char) otomatis 404 → `Status.CORRUPT` tanpa perlu logika tambahan: panjangnya salah, rute tak pernah matched.

Bagian LAIN dari brief (struktur `Checker(BaseChecker)`, `check()` cuma `GET /`, exception handling di `__main__`, pemakaian `A.encode_state`/`A.decode_state`/`A.status_for`) dipakai apa adanya — cocok dan tidak perlu diubah.

---

## Bug ditemukan: jalur `_lib` di brief Step 3 salah nesting

Brief Step 3 menyuruh:
```bash
docker cp checkers/enowars10/_lib $C:/checkers/eno10_greple/_lib
docker cp checkers/enowars10/greple/checker.py $C:/checkers/eno10_greple/checker.py
```
Ini menaruh `_lib` sebagai **child** dari `eno10_greple/`. Tapi checker.py (baris dari brief Step 1, dipakai verbatim) resolve `_lib` sebagai **sibling**:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
```
`parent.parent` dari `/checkers/eno10_greple/checker.py` adalah `/checkers`, jadi ia cari `/checkers/_lib` — BUKAN `/checkers/eno10_greple/_lib`. Terbukti langsung: gate pertama gagal `ModuleNotFoundError: No module named 'adlab_eno'` (exit 1, bukan status checklib apapun).

**Fix**: deploy `_lib` SEKALI ke `/checkers/_lib` (shared, sibling dari semua `eno10_*`), bukan digandakan ke dalam tiap direktori checker. Setelah dipindah, semua gate lolos. Sudah didokumentasikan sbg komentar di `checker.py` (baris setelah shebang) supaya 6 checker berikutnya (yang meng-copy header sys.path yang sama) tidak mengulang bug yang sama.

Detail teknis lain yang perlu dicatat untuk task berikutnya: `/checkers` di host adalah bind-mount `~/adlab/forcad/checkers` (dari `docker inspect forcad-celery-1`), dan celery mengeksekusi checker sebagai `uid=65534 (nobody)`. `docker exec $C mkdir/chmod` di brief Step 3 GAGAL permission-denied karena direktori dimiliki `reky` (uid 1000) mode 755, dan `nobody` bukan owner/group match. Solusinya: buat direktori & copy file langsung via SSH host (`mkdir`/`cp`/`chmod` sebagai `reky`, bukan `docker exec`), karena itu memang path host biasa — `docker exec` dgn user non-root cuma perlu bisa **read+execute**, bukan perlu bisa menulis ke sana.

---

## Masalah build service (bukan checker) — diperbaiki, TIDAK di-BLOCKED

Build `greple` (Zig 0.15.2 via `apk add zig` di alpine:3.23, sama persis dgn `minimum_zig_version` di `build.zig.zon`) gagal 2x murni karena masalah service:

1. **BuildKit tak tersedia**: `docker compose` di server ini tidak punya plugin `buildx` (`docker: unknown command: docker buildx`). Dockerfile asli pakai `RUN --mount=type=cache,...` yang butuh BuildKit murni. Compose sendiri fallback otomatis ke classic builder (cuma warning, bukan fatal) — tapi baris `--mount` tetap gagal di classic builder. **Fix**: hapus flag `--mount=type=cache,...` dari `RUN zig build` di `Dockerfile` SALINAN SERVER (`~/adlab/eno10/greple/Dockerfile`) — cache mount murni optimisasi rebuild, bukan kebutuhan fungsional. Source asli di laptop TIDAK disentuh.

2. **Drift API zig std**, 2 error kompilasi di `src/utils.zig`:
   - `var hash: Hash = undefined;` di `randomHash()` (baris 54) shadow deklarasi top-level `pub fn hash(data) Hash` (baris 40) → error compiler ("local variable shadows declaration"). Fix: rename jadi `var h: Hash = undefined;` (2 baris terkait ikut diubah).
   - `std.fs.cwd().writeFile(secret_path, &generated)` (2 pemanggilan, baris 19 & 29) — signature 2-argumen lama, sedang di zig 0.15.2 `Dir.writeFile` butuh 1 struct `WriteFileOptions{ sub_path, data, flags }` (dikonfirmasi baca langsung `/usr/lib/zig/std/fs/Dir.zig` di container alpine+zig). Fix: `std.fs.cwd().writeFile(.{ .sub_path = secret_path, .data = &generated })`.

   Kedua fix mekanis (rename variabel + update 1 signature call), diterapkan HANYA di salinan server (`~/adlab/eno10/greple/src/utils.zig`), tidak menyentuh source asli tim di laptop. Build sukses setelah patch ini (`Successfully built ... Successfully tagged greple_service-greple:latest`), container `Up` dan `Listening on port 7777` di log.

Karena build akhirnya sukses murni dgn 2 patch kecil, saya TIDAK melaporkan BLOCKED — gate berjalan penuh.

---

## Evidence gate (exact commands + output)

Server: `reky@192.168.43.136`. Service greple berjalan di host, network `forcad_default`, IP container `192.168.0.17:7777` (dikonfirmasi reachable dari celery: `docker exec $C curl -m5 -s -o /dev/null -w "http_code=%{http_code}\n" 192.168.0.17:7777/` → `http_code=200`, sebelum gate dimulai).

Deploy checker ke celery (setelah menemukan & memperbaiki bug `_lib` di atas):
```
~/adlab/forcad/checkers/_lib/adlab_eno.py           (shared, sibling dari semua eno10_*)
~/adlab/forcad/checkers/_lib/test_adlab_eno.py
~/adlab/forcad/checkers/eno10_greple/checker.py     (mode 755, owner reky:reky)
```

Gate run final (persis versi checker.py yang di-commit):
```
$ C=$(docker ps -qf name=forcad-celery | head -1); IP=192.168.0.17
$ FLAG="ENOTESTFLAG1785093456FINALAAAA="

$ docker exec $C /checkers/eno10_greple/checker.py check $IP; echo "check=$?"
check=101

$ docker exec $C /checkers/eno10_greple/checker.py put $IP "" "$FLAG" 0 > /tmp/f1.out 2>/tmp/f1.err; echo "put=$?"
put=101
$ cat /tmp/f1.out
{"pid":"b4ab26ca31c697fa3b4b243a12582b7793e5522a70a5472767c1424f"}

$ FID=$(cat /tmp/f1.out)
$ docker exec $C /checkers/eno10_greple/checker.py get $IP "$FID" "$FLAG" 0; echo "get=$?"
get=101

$ docker exec $C /checkers/eno10_greple/checker.py get $IP '{"pid":"deadbeef"}' "$FLAG" 0 >/tmp/f2.out 2>/tmp/f2.err; echo "corrupt=$?"
corrupt=102
$ cat /tmp/f2.err
[__main__.Checker.get:53] equality assertion failed: 404 (<class 'int'>) != 200 (<class 'int'>)

$ docker exec $C /checkers/eno10_greple/checker.py check 10.13.37.99 >/tmp/f3.out 2>/tmp/f3.err; echo "down=$?"
down=104
$ cat /tmp/f3.err
ConnectionError(MaxRetryError("HTTPConnectionPool(host='10.13.37.99', port=7777): Max retries exceeded with url: / (Caused by NewConnectionError('...Failed to establish a new connection: [Errno 113] No route to host'))"))
```

Semua exit code sesuai yang diminta: **101 / 101 / 101 / 102 / 104**.

(Ada satu gate run sebelumnya dengan `checker.py` versi tanpa komentar kontrak-deploy, hasilnya identik: `check=101 put=101 get=101` dengan `pid=7d4558294a222c4beb8945b52415807270c060799b8adc73fbaec737`, lalu `corrupt=102`, `down=104`. Setelah menambah komentar dokumentasi di checker.py, di-sync ulang ke server dan gate diulang penuh — hasilnya identik seperti di atas, jadi tidak ada regresi dari perubahan komentar.)

### Teardown (setelah gate lolos)
```
$ ~/adlab/enowars10-deploy.sh greple down
Container greple_service-greple-1 Stopping/Stopped/Removing/Removed
EXIT=0

$ docker ps -a --format "{{.Names}}" | grep -i greple
no greple containers

$ docker network inspect forcad_default --format "{{range .Containers}}{{.Name}} {{end}}"
(daftar 15 container forcad/adlab semula, greple sudah tidak ada)
```
Free memory server sebelum/sesudah: ~858Mi/6.3Gi available → ~995Mi/6.2Gi available (stabil, tidak ada resource yang bocor).

---

## File yang diubah/dibuat

- **`checkers/enowars10/greple/checker.py`** (baru, executable) — checker greple final, dgn komentar kontrak-deploy `_lib` di atas.
- **`deploy/enowars10-deploy.sh`** (baru, executable) — helper generik untuk 6 checker berikutnya:
  - Interface CLI sama persis dgn brief (`enowars10-deploy.sh <service-dir> [up|down]`).
  - **Ditambah** (di luar teks brief Step 2, karena brief sendiri cuma stub + catatan "batasan" tanpa implementasi nyata): pembuatan `docker-compose.override.yml` idempoten yang menempelkan SEMUA service compose ke network `forcad_default` (external) sambil mempertahankan network `default` proyek (utk servis multi-container spt app+db) — tanpa ini, `docker compose up -d --build` polos (isi asli brief) TIDAK membuat servis reachable dari celery sama sekali (servis pakai network project sendiri).
  - Mencetak IP tiap container di `forcad_default` setelah `up` — itu IP yang dipakai utk argumen `<svc-ip>` checker, bukan host IP / port-publish.
  - Komentar mendokumentasikan 3 gotcha yang ditemukan langsung di lapangan: BuildKit/buildx tak ada tapi compose fallback otomatis (baris `--mount` tetap harus dihapus manual), potensi drift API toolchain eksotik (referensi ke laporan ini utk contoh patch Zig), dan larangan mengubah source asli di laptop (patch di salinan server saja).
- **TIDAK diubah** (sesuai override task): `forcad/config.enowars10.yml` — tidak dibuat/didaftarkan, registrasi ditunda ke tahap roster resource-aware berikutnya seperti diminta.

Sisi server (tidak dicommit, bagian dari environment ForcAD, konsisten dgn pola checker lain yg sudah ada di sana — `eno_shetcode`, `faust_birthdaygram`, `saar_licenser`):
- `~/adlab/forcad/checkers/_lib/` (harness bersama, shared)
- `~/adlab/forcad/checkers/eno10_greple/checker.py`
- `~/adlab/eno10/greple/` (source rsync + 2 patch Zig + Dockerfile tanpa `--mount` + `docker-compose.override.yml`) — dipertahankan di server (tidak dihapus) supaya rebuild berikutnya (kalau ada tahap roster) tidak perlu ulang dari nol; hanya CONTAINER-nya yang di-teardown.

---

## Self-review

- **Faithfulness ke brief**: struktur `Checker(BaseChecker)`, method `check/put/get`, exception handling `__main__` dipakai verbatim. Deviasi HANYA pada 2 hal request-shape (field body, sumber+status id) yang eksplisit diantisipasi task ("iterasi bentuk request... ini diharapkan") — masing-masing diverifikasi langsung via curl thd service nyata sebelum ditulis ke checker, bukan tebakan.
- **Tidak ada state palsu**: setiap klaim exit code di atas adalah output asli dari run yang barusan dieksekusi (bukan disalin dari draf brief), termasuk run ulang penuh setelah edit komentar terakhir — tidak ada regresi.
- **Isolasi perubahan**: patch Zig (`utils.zig`, `Dockerfile`) HANYA di salinan rsync server (`~/adlab/eno10/greple`), source asli tim di laptop (`~/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/greple/`) tidak tersentuh — dicek ulang tidak ada `git status`/`diff` di sana krn itu bukan git repo yg dipantau task ini, tapi tidak ada operasi write ke path itu sama sekali setelah rsync awal.
- **Commit bersih**: `git add` eksplisit 2 file (bukan `git add -A`), dicek `git status --porcelain` sebelum commit — `.omc/` (punya orkestrator) tidak ikut ter-stage.
- **Resource server**: greple di-teardown, network attachment ikut hilang, free memory server kembali ke level semula (~6.2Gi available), tidak ada container/volume nyisa.
- **Kekhawatiran kecil (bukan blocker)**: file `~/adlab/eno10/greple/Dockerfile` & `src/utils.zig` di server sekarang BERBEDA dari source asli laptop (2 patch di atas). Kalau task roster berikutnya me-rsync ULANG dari laptop tanpa sadar akan overwrite (rsync default meng-overwrite file yg beda), patch harus diulang. Ini sudah dicatat di komentar `deploy/enowars10-deploy.sh` ("drift API stdlib... liat laporan ini") tapi TIDAK ada mekanisme otomatis (mis. patch file terpisah) — kalau mau lebih aman, could add a small greple-specific patch script, tapi diputuskan tidak perlu untuk scope task ini (servis sudah di-teardown, rebuild berikutnya adalah scope roster, bukan Task 2).

## Rekomendasi untuk 6 checker HTTP berikutnya

1. **Copy komentar kontrak `_lib` dari `checker.py` ini** — brief per-task kemungkinan mengulang instruksi deploy Step 3 yang sama (nesting `_lib` salah); jangan diikuti apa adanya, langsung deploy `_lib` ke `/checkers/_lib` (sudah ada, tinggal pastikan tetap ada / tidak perlu diulang kalau belum berubah dari Task 1).
2. **Selalu curl manual dulu** sebelum percaya bentuk request di brief — 2 dari 2 asumsi brief soal request-shape di task ini ternyata salah (field body, lokasi+status id). Recon report jelas cuma garis besar, bukan spek presisi.
2. **Pakai `deploy/enowars10-deploy.sh`** (sudah di-commit, sudah diuji jalan end-to-end) utk servis HTTP baru — tinggal rsync source lalu `enowars10-deploy.sh <svc> up`, override network dibuat otomatis sekali.
3. Kalau servis pakai bahasa/toolchain eksotik lain (Gleam/Hare/Rust/.NET/SimH per catatan spec), siapkan mental budget sama spt greple: 1-2 kegagalan build karena drift versi package manager adalah NORMAL, bukan alasan BLOCKED kecuali fix-nya butuh perubahan struktural besar (bukan rename var / 1 signature call).

---

## Fix Report (Post-Review)

### Finding: `Checker` construction inside `try` in `__main__`

Reviewer catatan: `c = Checker(sys.argv[2])` ada DI DALAM blok `try:`. Kalau
konstruksi pernah raise SEBELUM `c` ter-bind, klausa
`except c.get_check_finished_exception():` akan merujuk `c` yang belum ada
→ `NameError` lolos tak tertangkap, melumpuhkan safety net
`except Exception as e:` di bawahnya. Upstream ForcAD membuat instance
checker DI LUAR try justru untuk alasan ini. Tidak berdampak ke gate greple
(argv selalu valid di kelima gate run — `check`/`put`/`get`/corrupt/down —
jadi `c` selalu ter-bind), tapi file ini jadi template copy-paste utk Task
3–12, jadi wajib benar sebelum dipakai ulang.

**Fix** — hoist `c = Checker(sys.argv[2])` ke atas `try:`, persis usulan
reviewer, tidak ada perubahan lain:

```diff
 if __name__ == "__main__":
+    c = Checker(sys.argv[2])
     try:
-        c = Checker(sys.argv[2])
         c.action(sys.argv[1], *sys.argv[3:])
     except c.get_check_finished_exception():
         cquit(Status(c.status), c.public, c.private)
     except Exception as e:
         cquit(A.status_for(e), "checker error", repr(e))
```

Dikonfirmasi via `git diff` sebelum commit: diff persis 1 baris pindah
posisi (`+1/-1`), tidak ada perubahan lain di file.

### Verifikasi

Servis greple sudah di-teardown, jadi gate TIDAK diulang (sesuai arahan
reviewer — perubahan ini behavior-preserving utk semua jalur yang sudah
dibuktikan, karena argv selalu valid di kelima run gate sebelumnya).
Verifikasi dilakukan via compile check:

```
$ python3 -m py_compile checkers/enowars10/greple/checker.py && echo "PY_COMPILE_OK exit=$?"
PY_COMPILE_OK exit=0
```

`__pycache__/` hasil compile check dihapus lagi sebelum commit (tidak
dicommit).

### Commit

```
$ git add checkers/enowars10/greple/checker.py
$ git status --porcelain   # cuma checker.py yang staged; docs/superpowers/plans/...
                            # (modifikasi concurrent, bukan punya task ini) TIDAK ikut
```

Commit `a8ab85d` — `fix(eno10): hoist Checker construction outside try in greple __main__`.

**Catatan**: saat commit, `docs/superpowers/plans/2026-07-27-enowars10-checkers.md`
juga muncul modified di working tree (perubahan concurrent dari proses lain,
bukan dibuat oleh task ini) — TIDAK di-stage/commit, sesuai praktik
`git add` eksplisit per-file yang sudah dipakai sejak commit pertama task ini.
