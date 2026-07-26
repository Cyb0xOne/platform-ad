# Container penyerang — Fase 2

Menjalankan exploit A/D **asli** untuk membuktikan jalur serang end-to-end:
RCE → curi flag → submit ke ForcAD.

## Berkas
- `Dockerfile` — image dengan pwntools + pycryptodome + flask + itsdangerous.
- `run_attack.py` — orkestrator: jalankan exploit (subprocess) → saring flag → submit.
- `exploit_iv_rce.py` — **TIDAK disertakan di repo ini.** Ini exploit asli milik
  bank soal, punya lisensinya sendiri. Salin dari:
  `~/workspaces/cylab/ctf/attack-defense/saarctf-2025/Licenser/exploits/exploit_iv_rce.py`

## Pakai
```bash
# 1. sediakan exploit
cp .../saarctf-2025/Licenser/exploits/exploit_iv_rce.py .
# 2. build
docker build -t adlab/attacker .
# 3. serang: <ip-target> <token-penyerang> <user1,user2,...>
#    Jalankan di network forcad_default agar bisa menjangkau VM & flag receiver.
docker run --rm --network forcad_default -v "$PWD":/exploit adlab/attacker \
  run_attack.py 10.13.37.12 <TOKEN> "user1,user2,user3"
```

Daftar username target di A/D sungguhan datang dari `/api/client/attack_data/`
(butuh adapter `checker_type: pfr`); untuk demo diambil dari DB ForcAD.
