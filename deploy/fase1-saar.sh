#!/usr/bin/env bash
# FASE 1 (langkah 1/3) — pasang adapter saarCTF ke ForcAD dan siapkan gate.
#
# Yang dilakukan:
#   1. Menyalakan `adlab-redis` (Redis kecil khusus state adapter, tanpa auth).
#      Redis ForcAD tidak dipakai karena ber-password sementara fallback
#      standalone gamelib memanggil StrictRedis tanpa parameter password.
#   2. Merakit paket checker di ~/adlab/forcad/checkers/saar_licenser/
#   3. Menambah dependency adapter ke checkers/requirements.txt
#   4. Membangun ulang image celery (dependency checker masuk lewat blok
#      CUSTOMIZE di Dockerfile celery — bukan lewat env_path, yang cuma $PATH)
#
# Tidak mendaftarkan apa pun ke config.yml. Pendaftaran baru dilakukan setelah
# gate manual (put lalu get) memberi exit code 101 dua kali.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

ADLAB=$HOME/adlab
FORCAD=$ADLAB/forcad
SRC=$ADLAB/services/Licenser
PKG=$FORCAD/checkers/saar_licenser

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# ------------------------------------------------------------ 1. redis ------
say "Redis khusus adapter"
if [ -n "$(docker ps -qf name=adlab-redis)" ]; then
  echo "sudah jalan"
else
  docker rm -f adlab-redis >/dev/null 2>&1 || true
  docker run -d --name adlab-redis --restart unless-stopped \
    --network forcad_default --network-alias adlab-redis \
    redis:7-alpine >/dev/null
  echo "adlab-redis dinyalakan di network forcad_default"
fi

# ------------------------------------------------------------ 2. paket ------
say "Merakit paket checker di $PKG"
rm -rf "$PKG"
mkdir -p "$PKG/svc"
cp "$ADLAB/adapters/saar/saar_adapter.py"        "$PKG/"
cp "$ADLAB/adapters/saar/licenser/checker.py"    "$PKG/"
cp -r "$SRC/gamelib"                             "$PKG/gamelib"
cp "$SRC/checkers/interface.py"                  "$PKG/svc/"
cp "$SRC/checkers/config.toml"                   "$PKG/svc/"
chmod +x "$PKG/checker.py"
find "$PKG" -maxdepth 2 -name "*.py" -o -maxdepth 2 -name "*.toml" | sort

# ------------------------------------------------------- 3. dependency ------
say "Venv Python 3.12 untuk adapter saarCTF (blok CUSTOMIZE)"
# gamelib memakai f-string PEP 701 (kutip sama bersarang) yang hanya sah di
# Python >= 3.12; image celery ForcAD adalah python:3.11. Menaikkan Python
# untuk seluruh image berisiko ke runtime engine, jadi adapter saar diberi
# interpreter sendiri dan checker.py memilihnya lewat shebang.
DF=$FORCAD/docker_config/celery/Dockerfile.fast
if grep -q "UV_PYTHON_INSTALL_DIR" "$DF"; then
  echo "Dockerfile sudah dipatch"
else
  [ -f "$DF.orig" ] && cp "$DF.orig" "$DF" || cp "$DF" "$DF.orig"
  python3 - "$DF" <<'PY'
import sys
path = sys.argv[1]
src = open(path).read()
anchor = "COPY ./checkers/requirements.txt /checker_requirements.txt"
block = """# [adlab] interpreter terpisah untuk adapter saarCTF (butuh Python >= 3.12).
# UV_PYTHON_INSTALL_DIR WAJIB: secara default uv menaruh Python standalone di
# /root/.local/share/uv/python/, sedangkan /root ber-mode 0700 dan checker
# dijalankan ForcAD sebagai user `nobody`. Akibatnya interpreter tidak terbaca
# dan Python mati saat boot dengan pesan yang menyesatkan:
#     Fatal Python error: init_fs_encoding: failed to get the Python codec ...
#     ModuleNotFoundError: No module named 'encodings'
# chmod a+rX menutup sisa lubang izin pada venv dan interpreter.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN uv python install 3.12 \\
 && uv venv --python 3.12 /opt/venv-saar \\
 && VIRTUAL_ENV=/opt/venv-saar uv pip install requests redis pycryptodome \\
 && chmod -R a+rX /opt/uv-python /opt/venv-saar

"""
assert anchor in src, "anchor tidak ketemu di Dockerfile.fast"
open(path, "w").write(src.replace(anchor, block + anchor, 1))
print("Dockerfile.fast dipatch")
PY
fi

say "Dependency checker"
# BERKAS INI DIPAKAI BERSAMA SEMUA CHECKER — jangan ditimpa, tambahkan saja.
# Pelajaran mahal: versi pertama skrip ini menimpanya dengan `pycryptodome`
# saja, sehingga `checklib==0.7.0` hilang dari image. Akibatnya checker
# example (task kontrol) mati dengan `ModuleNotFoundError: No module named
# 'checklib'` di SEMUA tim — dan gejalanya muncul jauh dari sebabnya.
#
# Sudah ada di image dasar: requests, redis, tomllib.
# checklib  -> dibutuhkan checker example bawaan ForcAD
# pycryptodome -> dibutuhkan interface.py Licenser (modul `Crypto`)
REQFILE=$FORCAD/checkers/requirements.txt
[ -f "$REQFILE" ] || : > "$REQFILE"
for pkg in "checklib==0.7.0" "pycryptodome"; do
  name=${pkg%%=*}
  grep -qiE "^${name}([=<>]|$)" "$REQFILE" || echo "$pkg" >> "$REQFILE"
done
# buang komentar lama yang pernah ditulis versi skrip terdahulu
sed -i '/^#/d' "$REQFILE"
sort -u -o "$REQFILE" "$REQFILE"
cat "$REQFILE"

# ------------------------------------------------------------ 4. build ------
say "Membangun ulang image celery"
cd "$FORCAD"
# `control.py start` TIDAK cukup: dia hanya `compose up -d` dan akan memakai
# image lama, sehingga dependency baru di checkers/requirements.txt tidak
# pernah terpasang (gejalanya: ModuleNotFoundError saat gate dijalankan).
# `build` memaksa Dockerfile celery dijalankan ulang.
.venv/bin/python control.py build --fast
.venv/bin/python control.py start --fast

say "Selesai. Gate manual (harus 101 dua kali):"
cat <<'GATE'
  C=$(docker ps -qf name=forcad-celery | head -1)
  docker exec $C /checkers/saar_licenser/checker.py check 10.13.37.11; echo "exit=$?"
  docker exec $C /checkers/saar_licenser/checker.py put   10.13.37.11 '' 'TESTFLAG123=' 0; echo "exit=$?"
  # ambil baris stdout dari put, pakai sebagai flag_id di get:
  docker exec $C /checkers/saar_licenser/checker.py get   10.13.37.11 '<stdout-put>' 'TESTFLAG123=' 0; echo "exit=$?"
GATE
