"""Adapter: checker saarCTF (`gamelib`) -> kontrak checker ForcAD.

Dipakai oleh `checker.py` tiap service saarCTF; file ini pustakanya.

    from saar_adapter import run
    run(module='interface', cls='LicenserServiceInterface')

KENAPA ADAPTER INI PERLU
------------------------
1. ASAL FLAG. `ServiceInterface.get_flag(team, tick, payload)` MEMBANGKITKAN
   flag sendiri: HMAC-SHA256 dari `config.SECRET_FLAG_KEY` atas
   `struct.pack('<HHHH', tick, team_id, service_id, payload)`. ForcAD
   sebaliknya membuat flag di engine lalu menyerahkannya lewat argv.
   Karena itu metode tersebut di-monkeypatch.

2. NOMOR RONDE. ForcAD tidak mengirim nomor ronde ke checker. gamelib memakai
   `tick` sebagai bagian kunci Redis
   (`services:<nama>:<team>:<tick>:<key>`), jadi tick sintetis aman selama
   PUT dan GET memakai nilai yang sama — dititipkan lewat `flag_id`.

3. OBJEK TIM. gamelib meminta dataclass `Team(id, name, ip)`; ForcAD cuma
   mengirim host. Objeknya dirakit di sini.

CATATAN REDIS — MENYIMPANG DARI RENCANA AWAL
--------------------------------------------
Rencana semula memakai Redis ForcAD dengan indeks DB terpisah. Tidak jadi:
Redis ForcAD dilindungi password, sedangkan fallback standalone gamelib
memanggil `redis.StrictRedis(REDIS_HOST, db=REDIS_DB)` tanpa parameter
password sama sekali. Menambalnya berarti menambal gamelib. Lebih bersih
memakai Redis kecil tersendiri (`adlab-redis`, tanpa auth, di network
ForcAD) — sekaligus memisahkan state adapter dari state engine, sehingga
adapter yang rusak tidak bisa mengotori data permainan.

CATATAN FORMAT FLAG
-------------------
gamelib punya `get_flag_regex()` yang mengunci format `SAAR{...}`. Untuk
Licenser hal itu TIDAK menjadi masalah: `retrieve_flags` hanya melakukan
pemeriksaan substring (`flag.encode() not in content`), bukan pencocokan
regex. Service saarCTF lain WAJIB dicek ulang di titik ini sebelum dipakai.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import NoReturn

OK, CORRUPT, MUMBLE, DOWN, CHECKER_ERROR = 101, 102, 103, 104, 110

BASE = Path(__file__).resolve().parent


_REAL_STDOUT_FD = None


def _hijack_stdout():
    """Alihkan stdout checker ke stderr; simpan stdout asli untuk flag_id.

    Checker saarCTF mencetak diagnostik ke stdout dengan bebas (`print(f'> GET
    ...')`, `print(f'User / Pass: ...')`) karena di gameserver aslinya stdout
    hanyalah log. Di ForcAD stdout ADALAH nilai `flag_id` yang dikembalikan ke
    GET — jadi cetakan itu meracuni kontrak. Gejalanya:
        stdout(put) = "pwntools not available!\\nUser / Pass: Sour... / S5St..."
        get -> flag_id tidak bisa dibaca
    Dilakukan di level file descriptor, bukan `sys.stdout`, supaya cetakan dari
    pustaka C / subprocess ikut teralihkan.
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


def _status_from_exception(exc, gamelib):
    """Exception gamelib -> exit code ForcAD."""
    for name, code in (('OfflineException', DOWN),
                       ('MumbleException', MUMBLE),
                       ('FlagMissingException', CORRUPT)):
        klass = getattr(gamelib, name, None)
        if klass is not None and isinstance(exc, klass):
            return code
    # gamelib memperlakukan sebagian exception bawaan sebagai "service aneh"
    if isinstance(exc, (AssertionError, KeyError, ValueError, IndexError)):
        return MUMBLE
    if isinstance(exc, (EOFError, TimeoutError, OSError)):
        return DOWN
    return CHECKER_ERROR


def run(module, cls, service_dir='svc'):
    """Titik masuk. Menerjemahkan argv ForcAD ke pemanggilan checker saarCTF.

    Catatan sys.path: yang dimasukkan adalah BASE (induk dari `gamelib/`),
    BUKAN `BASE/gamelib`. `gamelib/gamelib.py` memakai relative import
    (`from . import flag_ids`), jadi gamelib WAJIB di-import sebagai paket.
    Menaruh `gamelib/` sendiri di sys.path membuat `gamelib.py` ter-import
    sebagai modul top-level dan relative import-nya langsung gagal:
        ImportError: attempted relative import with no known parent package
    """
    sys.path.insert(0, str(BASE))
    sys.path.insert(0, str(BASE / service_dir))

    # DIPAKSA, bukan setdefault. Container celery ForcAD SUDAH memasang
    # REDIS_HOST sendiri (redis engine, ber-password). Dengan setdefault nilai
    # itu bertahan, gamelib menyambung ke redis yang salah, dan gagal dengan
    #   redis.exceptions.AuthenticationError: HELLO must be called with the
    #   client already authenticated ...
    # Adapter wajib memakai redis-nya sendiri yang tanpa auth.
    os.environ['REDIS_HOST'] = os.environ.get('ADLAB_REDIS_HOST', 'adlab-redis')
    os.environ['REDIS_DB'] = os.environ.get('ADLAB_REDIS_DB', '3')

    if len(sys.argv) < 3:
        _quit(CHECKER_ERROR, '', f'argv kurang: {sys.argv}')

    action, host = sys.argv[1].lower(), sys.argv[2]
    rest = sys.argv[3:]
    flag = rest[1] if len(rest) >= 2 else ''

    _hijack_stdout()   # mulai sini semua cetakan checker jatuh ke stderr

    import gamelib

    # Flag berasal dari ForcAD. `tick`/`payload` diabaikan: flag ForcAD sudah
    # unik per (tim, ronde, service).
    gamelib.ServiceInterface.get_flag = lambda self, team, tick, payload=0: flag

    team_id = int(host.rsplit('.', 1)[-1]) if host.replace('.', '').isdigit() else abs(hash(host)) % 1000
    team = gamelib.Team(id=team_id, name=f'team{team_id}', ip=host)

    checker_module = __import__(module)
    checker = getattr(checker_module, cls)()

    try:
        if action == 'check':
            # `check_integrity` butuh tick meski tidak menyimpan state; jam
            # dinding cukup karena tidak ada pasangan PUT/GET yang harus cocok.
            checker.check_integrity(team, int(time.time()))
            _quit(OK, '', 'check_integrity lolos')

        if action == 'put':
            tick = int(time.time())
            checker.store_flags(team, tick)
            flag_id = ''
            try:
                flag_id = checker.get_flag_id(team, tick, 0)
            except Exception:  # flag_ids opsional; sebagian service tidak punya
                pass
            payload = json.dumps({'t': tick, 'id': flag_id}, separators=(',', ':'))
            _quit(OK, payload, f'store_flags tick={tick}')

        if action == 'get':
            raw = rest[0] if rest else ''
            try:
                tick = json.loads(raw)['t']
            except (ValueError, KeyError, TypeError):
                _quit(CHECKER_ERROR, '', f'flag_id tidak bisa dibaca: {raw!r}')
            checker.retrieve_flags(team, tick)
            _quit(OK, '', f'retrieve_flags tick={tick}')

        _quit(CHECKER_ERROR, '', f'aksi tidak dikenal: {action}')

    except SystemExit:
        raise
    except Exception as exc:
        _quit(_status_from_exception(exc, gamelib), '', traceback.format_exc())
