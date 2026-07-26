"""Adapter: checker FAUST (`ctf_gameserver.checkerlib`) -> kontrak checker ForcAD.

Dipakai oleh `checker.py` tiap service FAUST; file ini pustakanya.

    from faust_adapter import run
    run(module='template', cls='TemplateChecker')

KENAPA ADAPTER INI PERLU
------------------------
FAUST dan ForcAD punya model yang berbeda di tiga titik:

1. ASAL FLAG. `checkerlib.get_flag(tick)` MEMBANGKITKAN flag sendiri (HMAC dari
   secret), bukan menerimanya. ForcAD sebaliknya: flag dibuat engine lalu
   diserahkan ke checker lewat argv. Karena itu `get_flag` di-monkeypatch.

2. NOMOR RONDE. ForcAD tidak mengirim nomor ronde ke checker sama sekali
   (argv cuma host/flag_id/flag/vuln). Padahal checker FAUST memakai `tick`.
   Untuk birthdaygram, `tick` dipakai murni sebagai KUNCI STATE
   (`store_state(f"flag{tick}User")`) plus satu percabangan `tick % 5 == 1`.
   Jadi tick sintetis aman asal SAMA antara PUT dan GET — dan itu dijamin
   dengan menitipkannya di `flag_id`.

3. PROTOKOL RUNNER. `run_check()` menjalankan seluruh siklus sekaligus dan
   bicara protokol kontrol lewat stdin/stdout ke runner FAUST. Tidak dipakai;
   kelas checker di-instansiasi langsung dan tiap metode dipanggil sendiri.

TIGA JEBAKAN YANG SUDAH DITANGANI DI SINI
-----------------------------------------
* `_LOCAL_STATE_PATH` adalah global modul yang HANYA diisi oleh `run_check()`.
  Karena `run_check()` tidak dipakai, nilainya tetap None dan `store_state`
  akan `open(None)` lalu meledak. Harus diisi manual.
* `store_state` menulis relatif terhadap CWD. Tanpa CWD tetap per-tim, state
  hilang tiap ronde dan GET selalu CORRUPT.
* Checker birthdaygram menyusun URL sebagai `http://[{ip}]:3000` — notasi
  literal IPv6, karena FAUST CTF berjalan di IPv6. Dengan IPv4 kita urllib3
  menolaknya. Ditangani dengan menambal `requests.Session.request`, bukan
  dengan mengubah source checker.
"""

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import NoReturn

# --- kode status ForcAD (lihat docs/plan.md "Kontrak checker ForcAD") --------
OK, CORRUPT, MUMBLE, DOWN, CHECKER_ERROR = 101, 102, 103, 104, 110

BASE = Path(__file__).resolve().parent
STATE_ROOT = Path(os.environ.get('ADLAB_STATE_DIR', '/checkers/.state'))


_REAL_STDOUT_FD = None


def _hijack_stdout():
    """Alihkan stdout checker ke stderr; simpan stdout asli untuk flag_id.

    Checker FAUST mencetak ke stdout dengan bebas (logging, `set_flagid`
    mode lokal mencetak "Storing Flag ID: ..."). Di gameserver aslinya stdout
    hanyalah log; di ForcAD stdout ADALAH nilai `flag_id` yang dikembalikan ke
    GET, jadi cetakan itu meracuni kontrak. Dilakukan di level file descriptor
    agar cetakan dari pustaka C / subprocess ikut teralihkan.
    """
    global _REAL_STDOUT_FD
    sys.stdout.flush()
    _REAL_STDOUT_FD = os.dup(1)
    os.dup2(2, 1)


def _quit(code, public='', private='') -> NoReturn:
    """stdout -> public/flag_id, stderr -> debug privat, exit code -> status."""
    sys.stdout.flush()
    if _REAL_STDOUT_FD is not None:
        os.dup2(_REAL_STDOUT_FD, 1)   # kembalikan stdout asli
    if public:
        print(public)
    if private:
        print(private, file=sys.stderr)
    sys.stdout.flush()
    sys.exit(code)


def _patch_ipv6_bracket_urls():
    """`http://[10.13.37.11]:3000` -> `http://10.13.37.11:3000`.

    Kurung siku hanya sah untuk literal IPv6; urllib3 menolak IPv4 di dalamnya.
    Ditambal di lapisan requests supaya source checker tidak perlu disentuh.
    """
    import requests

    pattern = re.compile(r'^(\w+://)\[(\d{1,3}(?:\.\d{1,3}){3})\]')
    original = requests.Session.request

    def request(self, method, url, *args, **kwargs):
        return original(self, method, pattern.sub(r'\1\2', url), *args, **kwargs)

    requests.Session.request = request


def _setup_checkerlib(team_id, flag):
    """Pasang monkeypatch dan siapkan penyimpanan state lokal per-tim."""
    from ctf_gameserver import checkerlib
    from ctf_gameserver.checkerlib import lib as checkerlib_impl

    # 1. Flag datang dari ForcAD, bukan dibangkitkan checker. `tick` sengaja
    #    diabaikan: flag ForcAD sudah unik per (tim, ronde, service).
    checkerlib.get_flag = lambda _tick: flag

    # 2. Flag ID yang diumumkan checker ditangkap, nanti ikut ke stdout PUT.
    captured = {}
    checkerlib.set_flagid = lambda data: captured.__setitem__('flagid', data)

    # 3. State lokal. `_LOCAL_STATE_PATH` normalnya diisi `run_check()`; karena
    #    kita melewatinya, harus diisi sendiri — kalau tidak `open(None)`.
    state_dir = STATE_ROOT / f'faust-team{team_id}'
    state_dir.mkdir(parents=True, exist_ok=True)
    checkerlib_impl._LOCAL_STATE_PATH = str(state_dir / f'_{team_id}_state.json')

    # CWD tetap: sebagian checker juga menulis file bantu relatif ke CWD.
    os.chdir(state_dir)

    return checkerlib, captured


def _status_from(result, checkerlib):
    """CheckResult FAUST -> exit code ForcAD."""
    CheckResult = checkerlib.CheckResult
    return {
        CheckResult.OK: OK,
        CheckResult.DOWN: DOWN,
        CheckResult.FAULTY: MUMBLE,
        CheckResult.FLAG_NOT_FOUND: CORRUPT,
        CheckResult.RECOVERING: MUMBLE,
    }.get(result, CHECKER_ERROR)


def run(module, cls, service_dir='svc', vendor_dir='vendor', scratch_dirs=()):
    """Titik masuk. Menerjemahkan argv ForcAD ke pemanggilan checker FAUST.

    scratch_dirs: direktori yang diasumsikan ADA oleh checker tapi tidak pernah
    dibuatnya sendiri. Checker FAUST ditulis untuk runner FAUST, yang
    menyiapkan lingkungan kerja lebih dulu; di bawah ForcAD tidak ada yang
    melakukannya. Contoh nyata: `utils.py` birthdaygram memakai
    `CUR_DIR = "/tmp/"` yang dipatok mati lalu menulis gambar steganografi ke
    `CUR_DIR + "/flags/"`, dan gagal dengan
        FileNotFoundError: '/tmp//flags/xxxx.png'
    """
    sys.path.insert(0, str(BASE / vendor_dir))
    sys.path.insert(0, str(BASE / service_dir))

    for d in scratch_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    if len(sys.argv) < 3:
        _quit(CHECKER_ERROR, '', f'argv kurang: {sys.argv}')

    action, host = sys.argv[1].lower(), sys.argv[2]
    rest = sys.argv[3:]

    _hijack_stdout()   # mulai sini semua cetakan checker jatuh ke stderr
    _patch_ipv6_bracket_urls()

    # ForcAD tidak mengirim nomor tim; host dipakai sebagai identitas stabil.
    team_id = int(host.rsplit('.', 1)[-1]) if host.replace('.', '').isdigit() else abs(hash(host)) % 1000

    flag = rest[1] if len(rest) >= 2 else ''
    checkerlib, captured = _setup_checkerlib(team_id, flag)

    checker_module = __import__(module)
    checker = getattr(checker_module, cls)(host, team_id)

    try:
        if action == 'check':
            _quit(_status_from(checker.check_service(), checkerlib), '', 'check selesai')

        if action == 'put':
            # Tick sintetis: unik per PUT, dititipkan di flag_id agar GET memakai
            # kunci state yang sama. Detik-epoch membuat `tick % 5` tetap bervariasi.
            tick = int(time.time())
            status = _status_from(checker.place_flag(tick), checkerlib)
            payload = json.dumps({'t': tick, 'id': captured.get('flagid', '')},
                                 separators=(',', ':'))
            _quit(status, payload, f'put tick={tick}')

        if action == 'get':
            flag_id = rest[0] if rest else ''
            try:
                tick = json.loads(flag_id)['t']
            except (ValueError, KeyError, TypeError):
                _quit(CHECKER_ERROR, '', f'flag_id tidak bisa dibaca: {flag_id!r}')
            _quit(_status_from(checker.check_flag(tick), checkerlib), '', f'get tick={tick}')

        _quit(CHECKER_ERROR, '', f'aksi tidak dikenal: {action}')

    except SystemExit:
        raise
    except Exception:
        _quit(CHECKER_ERROR, '', traceback.format_exc())
