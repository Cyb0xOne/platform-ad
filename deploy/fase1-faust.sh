#!/usr/bin/env bash
# FASE 1 (langkah 2/3) — pasang adapter FAUST ke ForcAD dan siapkan gate.
#
# Yang dilakukan:
#   1. Vendor `ctf_gameserver.checkerlib` (6 berkas) — lihat alasan di bawah
#   2. Merakit paket checker di ~/adlab/forcad/checkers/faust_birthdaygram/
#   3. Menambah dependency checker ke checkers/requirements.txt (MENAMBAH,
#      tidak menimpa — berkas itu dipakai bersama semua checker)
#   4. Membangun ulang image celery
#
# Tidak mendaftarkan apa pun ke config.yml. Pendaftaran menyusul setelah gate
# manual (put lalu get) memberi exit code 101.
#
# CATATAN VERSI PYTHON: berbeda dengan adapter saarCTF, adapter FAUST TIDAK
# butuh interpreter sendiri. `checkerlib` yang di-vendor dan berkas checker
# birthdaygram sudah terbukti kompilasi & import bersih di Python 3.11 —
# versi bawaan image celery. Pin `requires-python >= 3.13` di repo
# ctf-gameserver berlaku untuk paket gameserver utuh (termasuk bagian web),
# bukan untuk checkerlib yang seluruhnya stdlib.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

ADLAB=$HOME/adlab
FORCAD=$ADLAB/forcad
SRC=$ADLAB/services/birthdaygram
PKG=$FORCAD/checkers/faust_birthdaygram
CGS=$ADLAB/vendor-src/ctf-gameserver

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# ------------------------------------------------------------ 1. vendor -----
say "Vendor ctf_gameserver.checkerlib"
if [ ! -d "$CGS" ]; then
  mkdir -p "$(dirname "$CGS")"
  git clone -q --depth 1 https://github.com/fausecteam/ctf-gameserver "$CGS"
fi
echo "source: $CGS"

# ------------------------------------------------------------ 2. paket ------
say "Merakit paket checker di $PKG"
rm -rf "$PKG"
mkdir -p "$PKG/svc" "$PKG/vendor/ctf_gameserver/lib"

cp "$ADLAB/adapters/faust/faust_adapter.py"           "$PKG/"
cp "$ADLAB/adapters/faust/birthdaygram/checker.py"    "$PKG/"
cp -r "$CGS/src/ctf_gameserver/checkerlib"            "$PKG/vendor/ctf_gameserver/"
cp "$CGS/src/ctf_gameserver/__init__.py"              "$PKG/vendor/ctf_gameserver/" 2>/dev/null \
  || : > "$PKG/vendor/ctf_gameserver/__init__.py"
for f in flag.py checkresult.py __init__.py; do
  cp "$CGS/src/ctf_gameserver/lib/$f" "$PKG/vendor/ctf_gameserver/lib/" 2>/dev/null || true
done
[ -f "$PKG/vendor/ctf_gameserver/lib/__init__.py" ] || : > "$PKG/vendor/ctf_gameserver/lib/__init__.py"

cp "$SRC/checker/template.py" "$SRC/checker/utils.py"  "$PKG/svc/"
chmod +x "$PKG/checker.py"
find "$PKG" -name "*.py" | sort

# ------------------------------------------------------- 3. dependency ------
say "Dependency checker (MENAMBAH, tidak menimpa)"
# Berkas ini dipakai bersama SEMUA checker. Menimpanya pernah menghapus
# checklib dan mematikan checker kontrol di semua tim.
REQFILE=$FORCAD/checkers/requirements.txt
[ -f "$REQFILE" ] || : > "$REQFILE"
# utils.py birthdaygram butuh: wonderwords, stegano, numpy, Pillow
for pkg in "checklib==0.7.0" "pycryptodome" "wonderwords" "stegano" "numpy" "Pillow"; do
  name=${pkg%%=*}
  grep -qiE "^${name}([=<>]|$)" "$REQFILE" || echo "$pkg" >> "$REQFILE"
done
sed -i '/^#/d' "$REQFILE"
sort -u -o "$REQFILE" "$REQFILE"
cat "$REQFILE"

# -------------------------------------------------- 3b. direktori state -----
say "Direktori state untuk adapter FAUST"
# `checkerlib.store_state` menulis berkas JSON per-tim; adapter mengarahkannya
# ke /checkers/.state.
#
# PENTING: /checkers di container adalah BIND MOUNT dari host
# (~/adlab/forcad/checkers), BUKAN isi image. Jadi `RUN mkdir` di Dockerfile
# percuma — mount menutupinya. Direktori harus dibuat DI HOST.
#
# Izin: host memilikinya sebagai uid 1000 (reky) mode 755, sedangkan ForcAD
# menjalankan checker sebagai `nobody`. Tanpa mode permisif:
#     PermissionError: [Errno 13] Permission denied: '/checkers/.state'
#
# Efek samping yang menguntungkan: karena bind mount, state bertahan melewati
# restart maupun rebuild container — tidak ada flag yang hangus karena itu.
mkdir -p "$FORCAD/checkers/.state"
chmod 1777 "$FORCAD/checkers/.state"
ls -ld "$FORCAD/checkers/.state"

# ------------------------------------------------ 3c. pustaka sistem --------
say "Pustaka sistem untuk cv2 (rantai stegano)"
# utils.py birthdaygram menyembunyikan flag di dalam gambar:
#     utils.py -> stegano.lsb -> stegano.lsb.generators -> cv2 (opencv-python)
# opencv-python butuh libGL.so.1 yang tidak ada di image slim:
#     ImportError: libGL.so.1: cannot open shared object file
# Alternatifnya mengganti ke opencv-python-headless, tapi `stegano` menarik
# opencv-python sebagai dependensinya sendiri sehingga keduanya bertabrakan
# memperebutkan modul `cv2`. Memasang pustaka sistemnya lebih deterministik.
DF=$FORCAD/docker_config/celery/Dockerfile.fast
if grep -q "libgl1" "$DF"; then
  echo "Dockerfile sudah memasang libgl1"
else
  python3 - "$DF" <<'PY'
import sys
path = sys.argv[1]
src = open(path).read()
anchor = "COPY ./checkers/requirements.txt /checker_requirements.txt"
block = """# [adlab] libGL untuk cv2 (dipakai stegano di checker birthdaygram)
RUN apt-get update \\
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \\
 && rm -rf /var/lib/apt/lists/*

"""
assert anchor in src, "anchor tidak ketemu"
open(path, "w").write(src.replace(anchor, block + anchor, 1))
print("Dockerfile.fast dipatch untuk libgl1")
PY
fi

# ------------------------------------------------------------ 4. build ------
say "Membangun ulang image celery"
cd "$FORCAD"
.venv/bin/python control.py build --fast
.venv/bin/python control.py start --fast

say "Selesai. Gate manual:"
cat <<'GATE'
  C=$(docker ps -qf name=forcad-celery | head -1)
  FLAG="ADLABF$(date +%s)AAAAAAAAAAAAAAAAAAA="
  docker exec $C /checkers/faust_birthdaygram/checker.py check 10.13.37.11 >/tmp/f1.out 2>/tmp/f1.err; echo "check exit=$?"
  docker exec $C /checkers/faust_birthdaygram/checker.py put 10.13.37.11 "" "$FLAG" 0 >/tmp/f2.out 2>/tmp/f2.err; echo "put exit=$?"
  FID=$(cat /tmp/f2.out)
  docker exec $C /checkers/faust_birthdaygram/checker.py get 10.13.37.11 "$FID" "$FLAG" 0 >/tmp/f3.out 2>/tmp/f3.err; echo "get exit=$?"
GATE
