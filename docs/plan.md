# Rencana: Platform A/D Internal Terpadu (ForcAD + Adapter + Dashboard Custom)

> Skema visual arsitektur, alur tick, dan urutan fase ada di **[`docs/skema.md`](skema.md)**.

## Context
User belajar & melatih tim internal Attack-Defense. Bank soal berisi 41 vulnerable service
(`~/workspaces/cylab/ctf/attack-defense/`) tapi berasal dari **5 framework checker berbeda &
tidak kompatibel**: FAUST `checkerlib`, saarCTF `gamelib`, ENOWARS `enochecker` (HTTP),
blitz custom `check.py`, omctf custom `checker.py`. User ingin **satu ekosistem** (dashboard +
checker jadi satu) untuk A/D sungguhan skala kecil (tick, skor, submit flag, multi-tim),
di-deploy ke server `reky@192.168.43.136`, dengan **dashboard buatan sendiri**.

Keputusan yang sudah disepakati:
- **Level 3 (A/D penuh) skala kecil** — tim internal untuk latihan.
- **Adopsi gameserver existing sebagai mesin + dashboard custom** (bukan bangun engine dari nol).
- **Mesin = ForcAD** (pure-Python, DB gampang dibaca dashboard).
- **MVP = 1 service per framework** (1 saarCTF + 1 FAUST + 1 ENOWARS), **ketiga adapter ditulis
  sekaligus di Fase 1** untuk membuktikan pola adapter generalis.
- **Topologi = 2 tim, satu VM vulnbox per tim (KVM/libvirt)** — tiap tim punya root penuh,
  bisa patch OS/firewall/service, dan reset lab = restore snapshot.
- **Dashboard custom = terlengkap**: scoreboard read-only + detail serang/bertahan + **panel kontrol admin**.

**Spesifikasi server (dicek via SSH read-only):** Archcraft/Arch, kernel 6.19 x86_64, 8 core,
15 GB RAM (13 GB free) + 16 GB swap, disk 460 GB (257 GB free), **Docker 29.4.0 + Compose 5.1.2**,
user `reky` di grup `docker` (tanpa sudo), ada KVM/libvirt. Sangat memadai.
⚠️ **Gotcha:** shell SSH non-interaktif PATH kosong (zsh tak load profile) → semua skrip via SSH
WAJIB set PATH eksplisit atau pakai `bash -lc`. `docker` ada di `/usr/sbin/docker`.

---

## Arsitektur (4 lapis)

1. **Game engine (adopsi): ForcAD** — postgres + redis + rabbitmq + celery (scheduler checker &
   flag lifetime) + flag receiver + engine tick/ronde + admin panel. Dikonfigurasi via `config.yml`.
   Jalan lewat `docker-compose.yml` + `control.py`.
2. **Vulnbox layer: 1 VM per tim.** 2 VM di jaringan libvirt, IP statis, masing-masing berisi docker
   + 3 service MVP dengan source di `/opt/adlab/<svc>` supaya tim bisa patch (lihat *Topologi*).
3. **Checker adapter layer (UNIFIKASI — inti glue buatan sendiri):** 1 checker format-ForcAD per
   service yang mendelegasikan ke checker asli tiap framework (lihat *Desain adapter*).
4. **Dashboard custom (buatan sendiri):** app web terpisah (container sendiri di server).
   - **Backend API (FastAPI)** — query READ-ONLY ke Postgres ForcAD (skor, SLA, flag, tick);
     endpoint admin untuk kontrol (start/stop ronde, kelola tim/task, trigger checker manual)
     via mekanisme resmi ForcAD (`control.py`, celery, field DB terdokumentasi).
   - **Frontend SPA ringan** — scoreboard grid, status SLA/serangan per-service, timeline tick,
     log curi-flag + grafik, **panel admin** (auth token).
   - Auth admin sederhana untuk aksi kontrol.

## Alur data (satu tick)
Celery ForcAD → tiap (tim, task) jalankan **adapter checker** → adapter taruh/ambil flag ke service
tim itu via checker asli → hasil (OK/DOWN + flag) disimpan di Postgres ForcAD. Penyerang exploit
service tim lain, submit flag curian ke flag receiver ForcAD → divalidasi → poin. Dashboard custom
baca Postgres → render; panel admin menulis aksi kontrol.

---

## Kontrak checker ForcAD (referensi terverifikasi)

Seksi ini mendikte seluruh desain adapter, jadi ditulis eksplisit. Sumber di *Referensi*.

**CLI yang dipanggil ForcAD:**
```
checker.py check <host>
checker.py put   <host> <flag_id> <flag> <vuln>
checker.py get   <host> <flag_id> <flag> <vuln>
```

**Exit code — nama berbeda di dua sisi, kode sama.** Adapter kita meng-`import checklib`, jadi kode
kita memakai kolom kiri; sedangkan log celery dan kolom DB memakai kolom kanan. Jangan bingung saat
membaca log (`CheckerVerdict (CHECK UP)` itu sama dengan `Status.OK`).

| `checklib.Status` (sisi checker) | Kode | `TaskStatus` ForcAD (sisi engine) | Arti |
|---|---|---|---|
| `OK` | 101 | `UP` | service sehat / flag ketemu |
| `CORRUPT` | 102 | `CORRUPT` | service jalan tapi flag tidak bisa diambil |
| `MUMBLE` | 103 | `MUMBLE` | service berperilaku salah |
| `DOWN` | 104 | `DOWN` | tidak bisa terhubung |
| `ERROR` | 110 | `CHECK_FAILED` | bug di checker itu sendiri |

> Diverifikasi langsung: `backend/lib/models/types.py:4-11` (engine) dan
> `python -c "import checklib"` di dalam container celery (checker). Ada **lima** kode, bukan empat.

**Aliran data & batasan yang penting:**
- Argumen `<flag_id>` yang diterima checker **selalu** `flag.private_flag_data`
  (`backend/lib/helpers/checkers.py:61,82`).
- **Ke mana stdout/stderr PUT disimpan tergantung tag `checker_type`**
  (`backend/lib/models/task.py:73-83`). `checker_type` adalah daftar tag dipisah `_`:

  | Tag | `public_flag_data` (tampil di scoreboard) | `private_flag_data` (→ jadi `flag_id` di GET) |
  |---|---|---|
  | *default* (tanpa tag) | kosong | **stdout** |
  | `pfr` | **stdout** | **stderr** |
  | `nfr` | kosong | token acak bawaan ForcAD (`secrets.token_hex(20)`) |

  → **Default itu privat.** State PUT→GET tidak bocor ke scoreboard kecuali kita minta.
  → **`pfr` memberi dua kanal sekaligus:** stdout jadi flag id publik untuk penyerang,
     stderr jadi state privat untuk GET. Ini yang kita pakai kalau service butuh flag id publik.
- **Tidak ada nomor ronde di argv.** Checker hanya tahu host, flag_id, flag, vuln.
- **PUT selalu dijalankan; GET hanya dijalankan kalau CHECK sukses.**
- `round_time` disarankan **≥ 4× `checker_timeout`** (minimal 3 aksi per ronde).
- Checker hidup di direktori `checkers/` **di dalam container celery**. Dependency tambahan masuk
  **blok CUSTOMIZE di Dockerfile celery** → **image celery wajib di-rebuild**.
  `env_path` **hanya menambah `$PATH`**, bukan cara memasang dependency Python.

**Struktur `config.yml`:**
- `game`: `round_time`, `flag_lifetime`, `start_time`, `timezone`, `default_score`, `game_hardness`,
  `inflation`, `checkers_path`
- `tasks[]`: `name`, `checker`, `checker_type` (`hackerdom` | `gevent`, plus tag `pfr` untuk public
  flag data), `checker_timeout`, `puts`, `gets`, `places`, `env_path`
- `teams[]`: `name`, `ip`, `highlighted`

**Menjalankan:** `./control.py setup` → `./control.py start --fast`.
Scoreboard `:8080`, admin panel `/admin/`, Flower `/flower/`.

### Disiplin stdout — berlaku untuk SEMUA adapter

Checker asli (saarCTF maupun FAUST) mencetak diagnostik ke **stdout** dengan bebas:
`print(f'> GET ...')`, `print(f'User / Pass: ...')`, `print('Storing Flag ID: ...')`. Di gameserver
aslinya itu tidak berbahaya — stdout cuma log. Di ForcAD **stdout ADALAH nilai `flag_id`**, jadi
cetakan itu meracuni kontrak. Gejalanya:

```
stdout(put) = "pwntools not available!\nUser / Pass: SourMariachi836 / S5StvvkY17w"
get         -> exit 110, "flag_id tidak bisa dibaca"
```

**Aturan: adapter WAJIB membajak stdout di level file descriptor** (`os.dup2(2, 1)`) sebelum
memanggil checker, lalu memulihkannya hanya untuk mencetak satu baris `flag_id`. Level fd, bukan
`sys.stdout`, supaya cetakan dari pustaka C dan subprocess ikut teralihkan.

### Variabel lingkungan: paksa, jangan `setdefault`

Container celery ForcAD **sudah** memasang `REDIS_HOST` untuk redis engine-nya sendiri (ber-password).
Adapter saarCTF yang memakai `os.environ.setdefault('REDIS_HOST', 'adlab-redis')` justru
mempertahankan nilai ForcAD, menyambung ke redis yang salah, dan gagal dengan
`redis.exceptions.AuthenticationError`. Nilai yang dituntut adapter harus **dipaksa**.

### Dua aturan desain yang lahir dari kontrak ini

1. **Aturan state.** Semua yang dibutuhkan GET di-encode adapter ke **satu baris JSON kompak**.
   Pilih kanalnya lewat tag `checker_type`:
   - **tanpa tag** → tulis state ke **stdout**; tidak ada yang bocor ke scoreboard. Ini default kita.
   - **`pfr`** → stdout = flag id publik yang memang harus dilihat penyerang (meniru perilaku asli
     saarCTF/ENOWARS yang mempublikasikan flag id), stderr = state privat untuk GET.
2. **Aturan tick.** Framework asli minta nomor tick tapi ForcAD tidak memberinya. Solusi seragam:
   saat **PUT/CHECK** tick dihitung dari jam (`(now - start_time) // round_time`, dibaca dari config
   ForcAD); saat **GET** tick diambil dari `flag_id` yang sudah membawanya sejak PUT.

---

## Berapa framework yang sebenarnya perlu adapter?

Premis awal "5 framework tidak kompatibel" **salah**. Setelah source tiap framework dibaca,
hanya **3** yang butuh adapter; 2 sisanya sudah memakai kontrak ForcAD apa adanya.

| Framework | Kondisi sebenarnya | Kerja |
|---|---|---|
| **omctf** | Sudah format ForcAD: `COMMANDS.get(sys.argv[1])(*sys.argv[2:])`, konstanta `OK, CORRUPT, MUMBLE, DOWN, CHECKER_ERROR = 101,102,103,104,110`, stdout publik / stderr privat | **drop-in** |
| **blitz** | Memakai `checklib` + `BaseChecker` — pustaka yang **sama persis** dengan contoh checker ForcAD; blok `__main__`-nya identik baris per baris | **drop-in** |
| **FAUST** `checkerlib` | Model aksi & flag berbeda total | adapter + injeksi flag |
| **saarCTF** `gamelib` | Model aksi & flag berbeda total | adapter + injeksi flag + redis |
| **ENOWARS** `enochecker3` | Checker berupa service HTTP | adapter HTTP + sidecar mongo |

Sebabnya: kontrak checker ForcAD itu turunan konvensi **Hackerdom** yang jadi standar de-facto di
satu garis keturunan sistem A/D. blitz dan omctf lahir dari garis itu, FAUST/saarCTF/ENOWARS tidak.

Konsekuensi rencana: blitz & omctf **tidak perlu menunggu Fase 5** — begitu 3 adapter jadi, keduanya
cukup disalin ke `checkers/` dan didaftarkan di `tasks[]`.

## Desain adapter per framework

Ketiganya dinormalisasi ke exit code ForcAD di atas.

### saarCTF (`gamelib`)

| ForcAD | gamelib |
|---|---|
| `check` | `check_integrity(team, tick)` |
| `put` | `store_flags(team, tick)` |
| `get` | `retrieve_flags(team, tick)` |

- **Injeksi flag:** `self.get_flag(team, tick, payload)` **membangkitkan flag dari secret** — tidak
  menerima flag dari luar. Adapter harus **monkeypatch** metode itu agar mengembalikan flag ForcAD.
- **State:** `self.store()` / `self.load_or_flagmissing()` butuh **Redis** (`REDIS_HOST`, `REDIS_DB`)
  → pakai Redis ForcAD dengan indeks DB terpisah supaya tidak bentrok dengan state engine.
- **Flag id:** tangkap `set_flag_id()` / `get_flag_id()` → keluarkan di stdout PUT.
- **Objek `Team`:** adapter membangun objek sintetis (id, name, ip) dari argumen ForcAD.
- **Status:** `OfflineException`→104 · `MumbleException`→103 · `FlagMissingException`→102 ·
  lolos tanpa exception→101 · exception lain→110.

### FAUST (`checkerlib`)

| ForcAD | checkerlib |
|---|---|
| `check` | `check_service()` |
| `put` | `place_flag(tick)` |
| `get` | `check_flag(tick)` |

- **Jangan pakai `run_check()`.** Fungsi itu menjalankan seluruh siklus (place + check + lookback
  ~5 tick) dan bicara protokol kontrol ke runner FAUST lewat stdin/stdout. Adapter meng-instansiasi
  kelas checker langsung lalu memanggil ketiga metode itu satu per satu.
- ⚠️ **`ctf-gameserver` tidak ada di PyPI, dan source-nya menuntut Python ≥ 3.13** sementara image
  celery ForcAD adalah **python:3.11**. Pin itu untuk paket gameserver utuh (termasuk bagian web),
  bukan untuk checkerlib. **Solusi: vendor minimal** — `checkerlib/` + `lib/flag.py` +
  `lib/checkresult.py` + dua `__init__.py`. Enam file, seluruhnya stdlib, terbukti meng-import
  bersih di Python 3.11. Tidak perlu Python 3.13 maupun virtualenv terpisah.
- `CheckResult` terverifikasi berisi persis: `OK`, `DOWN`, `FAULTY`, `FLAG_NOT_FOUND`, `RECOVERING`.
- **Injeksi flag:** `checkerlib.get_flag(tick)` juga **membangkitkan flag sendiri** — default-nya
  minta ke runner, atau (mode lokal) generate dummy dari secret hardcoded. Harus **di-monkeypatch**.
- **State:** `store_state`/`load_state` menulis `_{team}_state.json` **di CWD** → butuh direktori
  kerja per-tim yang persisten. Dipakai `/checkers/.state/faust-team<N>/`.
  ⚠️ Direktori itu harus dibuat **setelah** `COPY ./checkers /checkers` di Dockerfile celery dan
  ber-mode `1777`: checker dijalankan ForcAD sebagai user `nobody`, sedangkan `/checkers` milik
  root, sehingga tanpa itu adapter mati dengan
  `PermissionError: [Errno 13] Permission denied: '/checkers/.state'`.
  Konsekuensi yang diterima: state hidup selama container celery hidup — rebuild/restart
  menghapusnya, dan flag yang ditaruh sebelum restart jadi CORRUPT sampai `flag_lifetime` lewat.
  Kalau mengganggu, ganti dengan named volume. Bandingkan dengan adapter saarCTF yang **tidak**
  kena masalah ini karena state-nya di Redis, bukan filesystem.
- **Flag id:** tangkap `set_flagid(data)` → stdout PUT.
- **Status:** `CheckResult` `OK`→101 · `DOWN`→104 · `FAULTY`→103 · `FLAG_NOT_FOUND`→102 ·
  `RECOVERING`→103.
- ⚠️ **URL bergaya IPv6.** Checker `birthdaygram` menyusun URL sebagai `http://[{self.ip}]:3000`
  (`faustctf-2025/birthdaygram/checker/utils.py`) — FAUST CTF memang berjalan di IPv6, tapi VM kita
  IPv4. Adapter harus menormalkan host sebelum diserahkan ke checker (buang kurung siku untuk IPv4,
  atau beri VM alamat IPv6). Cek ini per service FAUST, jangan diasumsikan seragam.
- ⚠️ **Dependency berat.** `birthdaygram` menarik `wonderwords`, `stegano`, `numpy`, `Pillow` —
  ini yang bikin image celery membengkak dan memperbesar peluang bentrok versi.

### ENOWARS (`enochecker3`) — paling berat

- Checker asli adalah **service HTTP**, dan butuh **MongoDB** untuk ChainDB → perlu **dua container
  sidecar** (checker + mongo) di network yang sama dengan celery ForcAD. Ini komponen infrastruktur
  baru, bukan sekadar satu file adapter.
- **Bentuknya beda sendiri.** Dua adapter lain membungkus PUSTAKA (import checker asli, panggil
  metodenya). ENOWARS tidak bisa: checker-nya service HTTP. Jadi adapter ini **klien HTTP**, bukan
  pembungkus. Akibatnya semua kelas masalah adapter lain — versi Python, dependensi, izin berkas,
  stdout kotor — **lenyap**, terkurung di container checker. Gantinya muncul kebutuhan
  infrastruktur: dua sidecar di network `forcad_default`.

- **Kontrak kawat (diverifikasi dari paket `enochecker3==0.8.1`):** `POST /` dengan JSON
  beralias camelCase — `taskId, method, address, teamId, teamName, currentRoundId, relatedRoundId,
  flag, variantId, timeout, roundLength, taskChainId, flagRegex, flagHash, attackInfo`.
  **`timeout` dalam MILIDETIK** (checker memakai `task.timeout / 1000`).
  Balasan: `{"result": "OK"|"MUMBLE"|"OFFLINE"|"INTERNAL_ERROR", "message": ...}`.

- **Kunci fidelitas = `taskChainId`,** bukan roundId. `ChainDB` dikunci oleh nilai itu; data yang
  disimpan `putflag` (`db.set("userdata", ...)`) hanya terbaca `getflag` bila `taskChainId`
  identik. ForcAD tak punya konsep itu → adapter membangkitkannya saat PUT dan menitipkannya di
  `flag_id`, pola yang sama dengan tick pada dua adapter lain.

- **Pemetaan aksi:** `check`→`havoc` · `put`→`putflag` · `get`→`getflag`.
  **`vuln` ForcAD → `variantId` ENOWARS**, tapi ⚠️ **indeksnya bergeser satu**:

  ```python
  place = secrets.choice(range(1, task.places + 1))   # ForcAD: 1-BASED
  @checker.putflag(0) / (1) / (2)                     # ENOWARS: 0-BASED
  ```

  Meneruskan apa adanya membuat `places: 3` sesekali mengirim `variantId=3` yang tidak
  terdaftar → checker balas `INTERNAL_ERROR` → exit 110. **Gejalanya menipu:** hanya
  ~sepertiga PUT yang gagal, sementara `check` dan `get` tetap hijau — jadi gate manual
  sekali jalan bisa lolos tanpa menemukannya. Ketahuan dari kolom `command` di tabel
  `teamtasks` yang merekam argumen persis. Adapter memakai `variantId = vuln - 1`.
  Adapter saarCTF/FAUST tidak kena karena mengabaikan `vuln` sepenuhnya.

  `havoc` hanya terdaftar varian 0, jadi `check` mematok `variantId: 0` berapa pun vuln-nya.

- **Tidak perlu injeksi flag** — flag datang lewat payload request. Ini satu-satunya yang bersih.
- **Status:** `OK`→101 · `OFFLINE`→104 · `INTERNAL_ERROR`→110.
  `MUMBLE` dipetakan **bergantung aksi**: pada `get` → **CORRUPT (102)**, selain itu → MUMBLE (103).
  Alasannya: ENOWARS tidak membedakan "service aneh" dari "flag tidak ketemu" (keduanya MUMBLE),
  sementara ForcAD membedakannya — dan `getflag` yang gagal justru bermakna CORRUPT: service hidup
  tapi flag tak bisa diambil, yaitu jejak serangan yang berhasil.
- **Sidecar tak terjangkau → 110, bukan 104.** Itu kegagalan infrastruktur kita, bukan service tim;
  memetakannya ke DOWN akan menghukum tim atas kesalahan panitia.

---

## Topologi: VM per tim (KVM/libvirt)

- **2 VM** (`team1`, `team2`) di jaringan libvirt, **IP statis** lewat DHCP lease tetap. IP itulah
  yang masuk ke `teams[].ip` di `config.yml`.
- **Isi VM:** distro minimal + docker + 3 service MVP via compose, source di `/opt/adlab/<svc>`
  supaya tim bisa patch dengan root penuh (service, firewall, OS).
- **Provisioning:** siapkan satu base image, lalu `virt-clone` per tim. **Snapshot setelah
  provisioning** = reset lab satu perintah.
- **Distribusi image service — jangan biarkan tiap VM menarik dari internet.** Jalur internet
  server lewat hotspot dan lambat, dan biayanya berlipat karena setiap VM menarik sendiri.
  Jalur host→VM lewat `virbr` justru cepat (200 MB terkirim seketika saat diuji). Jadi untuk
  service MVP: build/pull **sekali di host**, lalu sebar:

  ```
  docker save <image> | ssh reky@10.13.37.11 'docker load'
  docker save <image> | ssh reky@10.13.37.12 'docker load'
  ```

  Bukti kenapa ini penting: saat cutover Fase 0.5, `docker build` example service di dalam VM
  harus menarik `python:3.11` (~1 GB) dan itu bagian paling lama dari seluruh fase.

**Anggaran resource:**

| Komponen | RAM | vCPU | Disk |
|---|---|---|---|
| Stack ForcAD (postgres+redis+rabbitmq+celery+nginx) | ~1,5–2 GB | 2 | ~5 GB |
| Dashboard custom | ~0,2 GB | – | kecil |
| VM tim ×2 | 3 GB each = 6 GB | 2 each = 4 | 20 GB each = 40 GB |
| **Total** | **~8 GB dari 13 GB free** | 8 dari 8 (oversubscribe wajar) | ~45 GB dari 257 GB |

**Batas skala:** 2 tim nyaman, 3 tim mepet, **4+ tidak** — turun ke 2 GB/VM membuat checker mulai
timeout, dan skor SLA jadi tidak jujur.

**⚠️ Gotcha jaringan — TERBUKTI, dan mekanismenya bukan iptables.** Container celery ForcAD ada di
bridge docker, VM ada di `virbr-adnet`. Libvirt di server ini memakai **backend nftables**; chain
`LIBVIRT_FWI` yang biasa disebut di dokumentasi lama **tidak ada**. Yang memblokir adalah chain
`guest_input` di tabel `ip libvirt_network`:

```
oif "virbr-adnet" ip daddr 10.13.37.0/24 ct state established,related accept
oif "virbr-adnet" counter packets 14 bytes 640 reject   <-- koneksi BARU mati di sini
```

Koneksi keluar dari VM lolos, koneksi masuk ke VM ditolak. Perbaikannya menyisipkan accept di atas
baris reject:

```
sudo nft insert rule ip libvirt_network guest_input \
  oif "virbr-adnet" ip daddr 10.13.37.0/24 accept
```

**Tidak persisten** — libvirt menulis ulang tabel itu tiap network restart / reboot host. Jalankan
ulang `deploy/fase05-gate.sh` setelah reboot, atau pasang systemd unit.

**Gate (sudah LOLOS):** dari container celery, TCP connect dan HTTP 200 ke `10.13.37.11:10000`
dan `10.13.37.12:10000`.

**⚠️ Blocker yang dicek paling pertama:** `reky` tercatat **tanpa sudo**, sementara membuat VM di
`qemu:///system` menuntut keanggotaan grup `libvirt`. Kalau yang tersedia hanya `qemu:///session`,
VM tidak dapat IP yang bisa dirutekan dan rencana VM harus dinegosiasi ulang (fallback: container
per tim di satu bridge `adnet`). Cek `id reky` dan `virsh -c qemu:///system list` **sebelum apa pun**.

---

## Pemilihan service MVP (final saat eksekusi; pilih image kecil + checker jalan)
- **saarCTF:** kandidat `Licenser`/`BlockRope` (punya exploit → uji jalur serang).
- **FAUST:** `birthdaygram` (Python, ★, paling gampang deploy/check).
- **ENOWARS:** `shetcode` (PHP, image kecil ~5.8 MB, enochecker paling sederhana).

## Layout
**Di server `~/adlab/`:** `forcad/` (engine + config.yml) · `dashboard/` (app custom) ·
`deploy/` (skrip) · image & definisi VM di libvirt.
**Di dalam tiap VM:** `/opt/adlab/<svc>/` (source vulnbox yang dipatch tim).
**Di repo:** `adapters/{saar,faust,eno}/` (source adapter, di-mount/copy ke `checkers/` ForcAD).
Skrip deploy dijalankan dari lokal via SSH dgn PATH eksplisit.

---

## Fase implementasi (inkremental, tiap fase terverifikasi)

- **Fase 0 — Fondasi:** cek akses libvirt → provisioning 2 VM (base image + `virt-clone`) →
  ForcAD hidup dengan example service bawaan + 2 tim.
  *Verif:* scoreboard `http://192.168.43.136:8080` tampil, tick jalan, example service ke-check OK.
- **Fase 0.5 — Gate konektivitas:** container celery bisa menjangkau kedua IP VM.
  *Verif:* `curl` dari dalam container celery ke port service di kedua VM. **Fase ini memblokir Fase 1.**
- **Fase 1 — Unifikasi:** rebuild image celery dgn dependency ketiga framework + sidecar
  enochecker/mongo → deploy 3 service MVP ke kedua VM → tulis 3 adapter.
  **Tiap adapter punya gate sendiri:** smoke test manual `put` lalu `get` dari CLI di dalam container
  celery, cek exit code, baru didaftarkan ke `config.yml`.
  *Verif:* ketiga service ke-check OK berkala untuk kedua tim. ← membuktikan tesis.
- **Fase 2 — Jalur serang: ✅ TERBUKTI.** Exploit RCE asli saarCTF (`exploit_iv_rce.py`, TANPA
  modifikasi) dijalankan dari container penyerang (`deploy/attacker/`) terhadap vulnbox lawan:
  RCE dapat shell (`uid=1000(licenser)`) → curi master secret → forge cookie sesi Flask → unduh
  app korban → dekripsi 4 flag ForcAD asli → submit ke flag receiver → **semua diterima**, skor
  penyerang naik (`stolen 4`), korban turun (`lost 4`), zero-sum. Jalur bertahan juga terbukti:
  `docker stop` service → ronde berikutnya `status 104 (DOWN)`, `checks_passed` tertinggal.
  Submit lewat `PUT /flags/` (via nginx `:8080`) dengan header `X-Team-Token`; body list flag
  ≤100 (satu request sekaligus juga menghindari rate-limit nginx yang membalas 429).
  Daftar username target di sini diambil dari DB sebagai oracle — di A/D sungguhan datang dari
  `/api/client/attack_data/` bila adapter di-set `checker_type: pfr`.
- **Fase 3 — Dashboard read-only: ✅ TERBUKTI.** App terpisah (`dashboard/`, FastAPI + SPA
  vanilla, container di network `forcad_default`, port `:8090`). Empat endpoint READ-ONLY ke
  Postgres ForcAD: `/api/scoreboard` (grid tim×service + ranking), `/api/timeline` (skor per
  ronde), `/api/attacks` (log serang: stolenflags ⋈ flags ⋈ teams), `/api/game` (ronde).
  UI: scoreboard grid dgn badge status (ikon+label, bukan warna saja), grafik timeline 2 tim
  (palet dataviz tervalidasi), tabel serangan; auto-refresh 5 dtk.
  **Verifikasi #1 terpenuhi:** total dashboard memakai formula ctftime PERSIS
  (`Σ score × checks_passed/checks`, `game.py:construct_ctftime_scoreboard`), dan cocok byte-for-byte
  dgn hitungan langsung dari `teamtasks`. Selisih vs endpoint `/ctftime/` engine murni live-vs-cached
  (engine pakai `get_cached_game_state`, dashboard live) — bukan beda formula.
  Kredensial DB lewat `.env` (tidak di-commit); `.env.example` sebagai template.
- **Fase 4 — Panel admin:** start/stop ronde, kelola tim/service, trigger checker manual.
- **Fase 5 — Perluasan:** tambah framework lain (blitz `check.py`, omctf `checker.py`) & service lain,
  + dokumen alur patch untuk tim. Tambah tim ke-3 **hanya kalau RAM mengizinkan**.

---

## Risiko / titik rawan

- **Injeksi flag = bagian tersulit.** saarCTF & FAUST membangkitkan flag sendiri dari secret; adapter
  harus mem-patch jalur itu tanpa merusak logika checker asli. ENOWARS bersih soal flag, tapi menuntut
  infrastruktur sendiri (HTTP + MongoDB).
- **Format flag.** Flag ForcAD punya format sendiri; **service** asli (bukan cuma checker) kadang
  memvalidasi format flag khas framework-nya. Injeksi yang lolos di sisi checker belum tentu lolos di
  sisi service — cek per service saat memilih MVP.
- **Umur flag vs lookback.** `flag_lifetime` ForcAD harus ≥ jendela lookback framework (FAUST memeriksa
  ~5 tick ke belakang); kalau tidak, GET gagal wajar dan SLA anjlok palsu.
- **Konflik versi Python — TERBUKTI, dan lebih tajam dari dugaan.** Ketiga pihak menuntut versi
  yang berbeda:

  | Pihak | Butuh | Bukti |
  |---|---|---|
  | ForcAD (engine) | 3.11 | image `forcad_base` |
  | FAUST `checkerlib` | repo pin ≥3.13, tapi kodenya jalan di 3.11 | vendor minimal → import bersih di 3.11 |
  | saarCTF `gamelib` | **≥3.12** | `SyntaxError: f-string: unmatched '('` — f-string PEP 701 di `connections.py:59` |

  **Mitigasi yang dipakai: virtualenv per adapter, dipilih lewat SHEBANG** — bukan `env_path`
  (yang hanya menambah `$PATH`). ForcAD mengeksekusi berkas checker langsung sebagai proses,
  jadi baris shebang-lah yang menentukan interpreter. Adapter saarCTF memakai
  `#!/opt/venv-saar/bin/python3`, dibuat di blok CUSTOMIZE `docker_config/celery/Dockerfile.fast`.
  Menaikkan Python untuk seluruh image ditolak: itu mempertaruhkan runtime engine demi satu adapter.

  **Tidak semua adapter perlu venv sendiri.** Adapter FAUST cukup dengan Python 3.11 bawaan image:
  `checkerlib` yang di-vendor maupun `template.py`/`utils.py` birthdaygram terbukti kompilasi &
  import bersih di 3.11, dan seluruh dependensinya (`wonderwords`, `stegano`, `numpy`, `Pillow`)
  terpasang di sana. Aturannya: **uji dulu di interpreter bawaan, tambahkan venv hanya kalau gagal.**

- **`checkers/requirements.txt` dipakai BERSAMA semua checker — tambahkan, jangan timpa.**
  Menimpanya (agar hanya berisi dependensi adapter baru) menghapus `checklib==0.7.0` dari image
  dan mematikan checker example di semua tim dengan `ModuleNotFoundError`, dengan gejala yang
  muncul jauh dari sebabnya. Skrip deploy menambah entri secara idempoten.
- **Routing jaringan** container celery → `virbr0` (lihat *Topologi*).
- **Akses libvirt tanpa sudo** — satu-satunya risiko yang bisa membatalkan pilihan VM.
- **Panel admin menulis ke ForcAD** berisiko korup state engine → batasi ke mekanisme ForcAD yang didukung.

---

## Verifikasi akhir (end-to-end)
1. Scoreboard ForcAD & dashboard custom menampilkan data sama (skor/SLA/tick 2 tim).
2. Ketiga service MVP ter-check OK untuk kedua tim tiap ronde.
3. Submit flag curian menaikkan skor penyerang; service dimatikan → SLA turun.
4. Aksi panel admin (start/stop ronde) tercermin di engine.

## Di luar cakupan (iterasi ini)
- Tidak menyatukan semua 41 service sekaligus (bertahap per framework setelah MVP).
- Tidak menulis exploit baru (pakai exploit asli yang sudah ada untuk uji).
- Tidak mengubah source service (hanya deploy + adapter + dashboard).
- Tidak menambah tim di luar 2 (dibatasi anggaran RAM).

---

## Referensi
Klaim teknis di dokumen ini diverifikasi ke sumber berikut:
- ForcAD — [README](https://github.com/pomo-mondreganto/ForcAD) · [wiki: Writing a checker](https://github.com/pomo-mondreganto/ForcAD/wiki/Writing-a-checker) · [`config.yml.example`](https://github.com/pomo-mondreganto/ForcAD/blob/master/config.yml.example) · [contoh checker](https://github.com/pomo-mondreganto/ForcAD/blob/master/tests/service/checker/checker.py)
- [`pomo-mondreganto/checklib`](https://github.com/pomo-mondreganto/checklib) — `status.py` (kode 101–110), `utils.py` (`cquit`: public→stdout, private→stderr)
- FAUST — [`ctf_gameserver/checkerlib/lib.py`](https://github.com/fausecteam/ctf-gameserver/blob/master/src/ctf_gameserver/checkerlib/lib.py)
- saarCTF — [`saarctf-gamelib`](https://github.com/MarkusBauer/saarctf-gamelib), `docs/howto_checkers.md`
- ENOWARS — dokumentasi `enochecker3`

## Catatan proses
Langkah berikutnya = rencana implementasi detail per fase, lalu eksekusi **Fase 0** di server.
