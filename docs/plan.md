# Rencana: Platform A/D Internal Terpadu (ForcAD + Adapter + Dashboard Custom)

## Context
User belajar & melatih tim internal Attack-Defense. Bank soal berisi 41 vulnerable service
(`~/workspaces/cylab/ctf/attack-defense/`) tapi berasal dari **5 framework checker berbeda &
tidak kompatibel**: FAUST `checkerlib`, saarCTF `gamelib`, ENOWARS `enochecker` (HTTP),
blitz custom `check.py`, omctf custom `checker.py`. User ingin **satu ekosistem** (dashboard +
checker jadi satu) untuk A/D sungguhan skala kecil (tick, skor, submit flag, multi-tim),
di-deploy ke server `reky@192.168.43.136`, dengan **dashboard buatan sendiri**.

Keputusan yang sudah disepakati lewat brainstorming:
- **Level 3 (A/D penuh) skala kecil** — tim internal untuk latihan.
- **Adopsi gameserver existing sebagai mesin + dashboard custom** (bukan bangun engine dari nol).
- **Mesin = ForcAD** (sudah ada di `tools/ForcAD`, pure-Python, DB gampang dibaca dashboard).
- **MVP = 1 service per framework** (1 saarCTF + 1 FAUST + 1 ENOWARS) untuk buktikan pola adapter generalis.
- **Topologi = 2 tim, docker network per-tim** (tiap tim vulnbox sendiri, bisa patch independen).
- **Dashboard custom = terlengkap**: scoreboard read-only + detail serang/bertahan + **panel kontrol admin**.

**Spesifikasi server (dicek via SSH read-only):** Archcraft/Arch, kernel 6.19 x86_64, 8 core,
15 GB RAM (13 GB free) + 16 GB swap, disk 460 GB (257 GB free), **Docker 29.4.0 + Compose 5.1.2**,
user `reky` di grup `docker` (tanpa sudo), ada KVM/libvirt. Sangat memadai.
⚠️ **Gotcha:** shell SSH non-interaktif PATH kosong (zsh tak load profile) → semua skrip via SSH
WAJIB set PATH eksplisit atau pakai `bash -lc`. `docker` ada di `/usr/sbin/docker`.

## Arsitektur (4 lapis)
1. **Game engine (adopsi): ForcAD** — postgres + redis + celery (scheduler checker & flag lifetime) +
   flag receiver + engine tick/ronde + admin panel. Dikonfigurasi via `config.yml` (teams, tasks,
   `round_time`, `flag_lifetime`). Jalan lewat `tools/ForcAD/docker-compose.yml` + `control.py`.
2. **Vulnbox layer (deployment per-tim):** 2 tim × 3 service MVP. Tiap tim = docker network terisolasi,
   IP internal sendiri, **source bind-mount** (`~/adlab/teams/teamN/<svc>/`) supaya tim patch lalu
   `docker compose up -d --build <svc>`. Skrip generator membuat & menjalankan stack per-tim.
3. **Checker adapter layer (UNIFIKASI — inti glue buatan sendiri):** ForcAD memanggil checker dalam
   FORMATNYA (aksi put/get/check + flag + flag_id + host tim tiap ronde). Kita tulis **1 checker
   format-ForcAD per service** yang mendelegasikan ke checker asli:
   - **saarCTF adapter** → panggil `gamelib.ServiceInterface` (store/retrieve/check_integrity),
     map flag/flag_id ForcAD ↔ flag/round saar (butuh redis — pakai redis ForcAD/redis kecil).
   - **FAUST adapter** → bungkus `checkerlib.BaseChecker` (place_flag/check_flag/check_service)
     single-shot, map status → exit code ForcAD.
   - **ENOWARS adapter** → checker asli jalan sebagai container HTTP (enochecker3); adapter HTTP-POST
     method PUTFLAG/GETFLAG/HAVOC dgn flag+flagId, terjemahkan JSON (OK/MUMBLE/OFFLINE).
   Semua dinormalisasi ke exit code ForcAD: UP 101 / CORRUPT 102 / MUMBLE 103 / DOWN 104.
4. **Dashboard custom (buatan sendiri):** app web terpisah (container sendiri di server).
   - **Backend API (FastAPI)** — query READ-ONLY ke Postgres ForcAD (skor, SLA, flag, tick);
     endpoint admin untuk kontrol (start/stop ronde, kelola tim/task, trigger checker manual)
     via mekanisme resmi ForcAD (`control.py`, celery, field DB terdokumentasi).
   - **Frontend SPA ringan** — scoreboard grid, status SLA/serangan per-service, timeline tick,
     log curi-flag + grafik, **panel admin** (auth token).
   - Auth admin sederhana untuk aksi kontrol.

## Alur data (satu tick)
Celery ForcAD → tiap (tim, task) jalankan **adapter checker** → adapter taruh/ambil flag ke service
tim itu via checker asli → hasil (UP/DOWN + flag) disimpan di Postgres ForcAD. Penyerang exploit
service tim lain, submit flag curian ke flag receiver ForcAD → divalidasi → poin. Dashboard custom
baca Postgres → render; panel admin menulis aksi kontrol.

## Pemilihan service MVP (final saat eksekusi; pilih image kecil + checker jalan)
- **saarCTF:** kandidat `Licenser`/`BlockRope` (punya exploit → uji jalur serang).
- **FAUST:** `birthdaygram` (Python, ★, paling gampang deploy/check).
- **ENOWARS:** `shetcode` (PHP, image kecil ~5.8 MB, enochecker paling sederhana).

## Layout di server `~/adlab/`
`forcad/` (engine + config.yml) · `teams/team1|team2/<svc>/` (source vulnbox, bind-mount) ·
`adapters/{saar,faust,eno}/` (checker adapter) · `dashboard/` (app custom) · `deploy/` (skrip).
Skrip deploy dijalankan dari lokal via SSH dgn PATH eksplisit.

## Fase implementasi (inkremental, tiap fase terverifikasi)
- **Fase 0 — Engine hidup:** ForcAD + example service bawaan + 2 tim di server. Verif: scoreboard
  `http://192.168.43.136:8080` tampil, tick jalan, example service ke-check UP.
- **Fase 1 — Unifikasi:** deploy 3 service MVP untuk 2 tim (network per-tim) + tulis 3 adapter.
  Verif: ketiga service ke-check UP berkala untuk kedua tim (log/DB ForcAD). ← membuktikan tesis.
- **Fase 2 — Jalur serang:** pakai exploit asli (saarCTF) curi flag team2 → submit ke ForcAD →
  skor bergerak; matikan 1 service → SLA turun.
- **Fase 3 — Dashboard read-only:** scoreboard + detail serang/bertahan + timeline.
- **Fase 4 — Panel admin:** start/stop ronde, kelola tim/service, trigger checker manual.
- **Fase 5 — Perluasan:** tambah framework lain (blitz `check.py`, omctf `checker.py`) & service lain,
  + dokumen alur patch untuk tim.

## Risiko / titik rawan
- **Fidelitas adapter** = bagian tersulit: checker asli menyimpan state (flag_id/round) beda dgn ForcAD;
  tiap adapter perlu mapping hati-hati. ENOWARS (checker HTTP) paling rumit; sebagian butuh redis/mongo sendiri.
- **Routing jaringan:** ForcAD akses tim via IP; network per-tim harus terjangkau container checker ForcAD
  (attach checker ke network tim / routing host).
- **Panel admin menulis ke ForcAD** berisiko korup state engine → batasi ke mekanisme ForcAD yang didukung.

## Verifikasi akhir (end-to-end)
1. Scoreboard ForcAD & dashboard custom menampilkan data sama (skor/SLA/tick 2 tim).
2. Ketiga service MVP ter-check UP untuk kedua tim tiap ronde.
3. Submit flag curian menaikkan skor penyerang; service mati → SLA turun.
4. Aksi panel admin (start/stop ronde) tercermin di engine.

## Di luar cakupan (iterasi ini)
- Tidak menyatukan semua 41 service sekaligus (bertahap per framework setelah MVP).
- Tidak menulis exploit baru (pakai exploit asli yang sudah ada untuk uji).
- Tidak setup VM per-tim (KVM tersedia untuk opsi masa depan, bukan sekarang).
- Tidak mengubah source service (hanya deploy + adapter + dashboard).

## Catatan proses
Setelah plan ini disetujui, langkah berikut = buat rencana implementasi detail (skill writing-plans),
lalu eksekusi Fase 0 dulu di server sebelum lanjut.
