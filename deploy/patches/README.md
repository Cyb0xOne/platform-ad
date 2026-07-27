# Patch build service enowars10

Tiga service enowars10 tidak bisa dibangun apa adanya di lab ini. Selama Task 2–7
patch-nya hanya hidup di salinan server (`~/adlab/eno10/<service>`), tidak di repo —
artinya `rsync` ulang dari sumber bersih akan mengulang kegagalan yang sama.
Berkas di direktori ini menutup utang itu.

**Sumber bersih** (tidak pernah disentuh):
`~/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/<service>/`

## Cara pakai

Salin sumber bersih ke server, lalu terapkan patch:

```bash
rsync -a --rsync-path=/usr/bin/rsync \
  ~/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/greple/ \
  reky@192.168.43.136:adlab/eno10/greple/

ssh reky@192.168.43.136 'export PATH=/usr/bin:/bin; cd adlab/eno10/greple && patch -p1' \
  < deploy/patches/greple.patch
```

Verifikasi dengan `patch -p1 --dry-run` lebih dulu kalau ragu.

## Isi tiap patch

### `greple.patch`
1. **`Dockerfile`** — buang `--mount=type=cache` pada `RUN zig build`.
   Docker di server utama tidak punya BuildKit, dan flag itu gagal di classic
   builder. Murni optimisasi rebuild, bukan kebutuhan fungsional.
2. **`src/utils.zig`** — patch *source*, bukan sekadar build. Toolchain Zig di
   image lebih baru daripada yang diasumsikan service: `std.fs.cwd().writeFile()`
   berubah dari `(path, data)` jadi bentuk struct `.{ .sub_path, .data }`. Juga
   rename variabel `hash` yang bentrok dengan nama tipe di `randomHash()`.

### `flagdrive.patch`
1. **`Dockerfile`** — buang lima blok `--mount=type=cache` (alasan sama).
2. **`frontend/index.html`** — perbaikan bug **upstream**, bukan penyesuaian lab.
   `href` aset `tailwind-css` menunjuk `style/tailwind.css` (path keluaran hook)
   padahal sumber sebenarnya `src/styles/tailwind.css`. Membuat build kalah balapan
   dengan pipeline aset Trunk.

### `funsplash.patch`
Dependency `bravo` adalah git dependency ke `github.com`, dan sandbox build tidak
bisa menjangkau host itu di port 443 — sementara `codeload.github.com` dan
`raw.githubusercontent.com` justru lancar (blokir berbasis hostname/SNI, bukan
GitHub down).

Patch mengarahkan `gleam.toml` + `manifest.toml` ke path lokal `../vendor/bravo`,
dan `Dockerfile` menyalin `./vendor` masuk sebelum `gleam deps download`.

**Patch ini butuh langkah tambahan** — direktori `vendor/bravo` (±220 KB) tidak
ikut di sini. Vendor ulang commit yang persis dipatok manifest:

```bash
mkdir -p vendor && cd vendor
curl -sL https://codeload.github.com/bird-dancer/bravo/tar.gz/d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9 \
  | tar xz
mv bravo-d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9 bravo
```

Commit `d87b8a4a04d6d370bb54ed6c512a907aa1e43fe9` bukan pilihan bebas — itu commit
yang sudah dipatok `manifest.toml` asli, jadi vendoring ini tidak mengubah versi
dependency, hanya cara mengambilnya.

## Catatan

Docker di **VM tim** (`10.13.37.11` / `10.13.37.12`) punya BuildKit yang berfungsi,
tidak seperti host server. Untuk service yang hanya butuh `--mount=type=cache`,
membangun di VM menghindari patch sama sekali (terbukti di Task 8). Patch
`utils.zig` dan `index.html` tetap perlu di mana pun dibangun — keduanya bukan soal
BuildKit.
