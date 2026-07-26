# Container penyerang untuk Fase 2 — menjalankan exploit A/D asli.
#
# Kenapa container tersendiri: exploit saarCTF butuh tumpukan dependency yang
# TIDAK ada di image mana pun yang sudah kita punya — pwntools (untuk `asm()`
# merakit shellcode saat runtime, butuh binutils), pycryptodome, plus flask +
# itsdangerous untuk memalsukan cookie sesi Flask. Menyatukannya ke image lain
# hanya akan mengotori mereka.
#
# Dijalankan di network forcad_default supaya bisa menjangkau VM tim lewat
# jalur yang sama dengan checker (rule nftables Fase 0.5). Di A/D sungguhan
# exploit ini jalan dari vulnbox tim penyerang; di sini dari host demi
# kemudahan, jalur jaringannya setara.

FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils gcc \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      pwntools pycryptodome flask itsdangerous requests

WORKDIR /exploit
COPY exploit_iv_rce.py /exploit/

ENTRYPOINT ["python3"]
