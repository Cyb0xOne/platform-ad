"""Adapter: checker ENOWARS (`enochecker3`) -> kontrak checker ForcAD.

Dipakai oleh `checker.py` tiap service ENOWARS; file ini pustakanya.

    from eno_adapter import run
    run(base_url='http://adlab-eno-shetcode:8000')

BENTUKNYA BEDA SENDIRI
----------------------
Dua adapter lain membungkus PUSTAKA: mereka meng-import checker asli lalu
memanggil metodenya. ENOWARS tidak bisa begitu — checker-nya adalah SERVICE
HTTP (`enochecker3` di balik gunicorn/uvicorn) yang menyimpan state di
MongoDB. Jadi adapter ini bukan pembungkus, melainkan KLIEN HTTP.

Konsekuensinya:
  * tidak ada masalah versi Python, dependensi, izin berkas, atau stdout kotor
    — semuanya terkurung di container checker;
  * sebagai gantinya muncul kebutuhan infrastruktur: dua container sidecar
    (checker + mongo) harus hidup di network yang sama dengan celery ForcAD.

KONTRAK KAWAT (diverifikasi dari paket enochecker3 0.8.1)
---------------------------------------------------------
POST /  dengan JSON beralias camelCase:
    taskId, method, address, teamId, teamName, currentRoundId,
    relatedRoundId, flag, variantId, timeout, roundLength, taskChainId,
    flagRegex, flagHash, attackInfo
`timeout` dalam MILIDETIK (checker memakai `task.timeout / 1000`).
Balasan: {"result": "OK"|"MUMBLE"|"OFFLINE"|"INTERNAL_ERROR", "message": ...}

KUNCI KESETIAAN: `taskChainId`
------------------------------
`ChainDB` di sisi checker dikunci oleh `taskChainId`. Data yang disimpan
`putflag` (`db.set("userdata", ...)`) hanya bisa dibaca `getflag` bila
`taskChainId`-nya IDENTIK. ForcAD tidak punya konsep itu, jadi adapter
membangkitkannya saat PUT dan menitipkannya di `flag_id` — persis pola yang
sama dengan tick pada adapter saarCTF/FAUST.

PEMETAAN AKSI
-------------
    ForcAD check -> method=havoc   (varian 0; shetcode hanya punya havoc(0))
    ForcAD put   -> method=putflag (varian = nomor `vuln` dari ForcAD)
    ForcAD get   -> method=getflag (varian dibaca kembali dari flag_id)
"""

import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from typing import NoReturn

OK, CORRUPT, MUMBLE, DOWN, CHECKER_ERROR = 101, 102, 103, 104, 110


def _quit(code, public='', private='') -> NoReturn:
    """stdout -> public/flag_id, stderr -> debug privat, exit code -> status."""
    if public:
        print(public)
    if private:
        print(private, file=sys.stderr)
    sys.exit(code)


def _post(base_url, payload, timeout_s):
    """Kirim satu pesan tugas ke checker dan kembalikan balasannya."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url.rstrip('/') + '/',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())


def _status(result, action):
    """Hasil enochecker3 -> exit code ForcAD.

    Satu keputusan yang perlu dijelaskan: pada aksi GET, `MUMBLE` dipetakan ke
    CORRUPT (102), bukan MUMBLE (103). ENOWARS tidak membedakan "service aneh"
    dari "flag tidak ketemu" — keduanya MUMBLE. ForcAD membedakannya, dan pada
    GET yang gagal makna A/D-nya justru CORRUPT: service hidup tapi flag tidak
    bisa diambil, yaitu jejak serangan yang berhasil. Pada CHECK/PUT tidak ada
    flag yang dicari, jadi MUMBLE tetap MUMBLE.
    """
    if result == 'OK':
        return OK
    if result == 'OFFLINE':
        return DOWN
    if result == 'MUMBLE':
        return CORRUPT if action == 'get' else MUMBLE
    return CHECKER_ERROR


def run(base_url, service_name='service'):
    """Titik masuk. Menerjemahkan argv ForcAD ke pesan tugas enochecker3."""
    if len(sys.argv) < 3:
        _quit(CHECKER_ERROR, '', f'argv kurang: {sys.argv}')

    action, host = sys.argv[1].lower(), sys.argv[2]
    rest = sys.argv[3:]
    flag = rest[1] if len(rest) >= 2 else ''

    # PENTING — PERGESERAN INDEKS. Nomor `vuln` ForcAD 1-BASED:
    #     place = secrets.choice(range(1, task.places + 1))
    #         (backend/services/tasks/actions.py)
    # sedangkan `variantId` ENOWARS 0-BASED (putflag(0), putflag(1), ...).
    # Meneruskannya apa adanya membuat `places: 3` mengirim variantId=3 yang
    # tidak terdaftar, dan checker membalas INTERNAL_ERROR -> exit 110.
    # Gejalanya menipu: hanya SEPERTIGA put yang gagal (saat vuln kebetulan 3),
    # sementara check dan get tetap hijau.
    raw_vuln = int(rest[2]) if len(rest) >= 3 and rest[2].isdigit() else 1
    vuln = max(0, raw_vuln - 1)

    # ForcAD tidak mengirim nomor tim; oktet terakhir host dipakai sebagai
    # identitas stabil, sama seperti pada adapter lain.
    team_id = int(host.rsplit('.', 1)[-1]) if host.replace('.', '').isdigit() else abs(hash(host)) % 1000
    timeout_s = 25

    base = {
        'taskId': 1,
        'address': host,
        'teamId': team_id,
        'teamName': f'team{team_id}',
        'timeout': timeout_s * 1000,     # MILIDETIK
        'roundLength': 180000,
        'flagRegex': '[A-Z0-9]{31}=',
        'flagHash': None,
        'attackInfo': None,
        # `relatedRoundId` WAJIB integer — tidak boleh None sekalipun aksinya
        # `havoc` yang tak terkait ronde mana pun. Menyetelnya None membuat
        # checker menolak seluruh permintaan:
        #   HTTP 422 {"loc":["body","relatedRoundId"],
        #             "msg":"none is not an allowed value"}
        # Untuk check/put disamakan dengan currentRoundId; untuk get diisi
        # ronde saat flag ditaruh (dibaca dari flag_id).
        'relatedRoundId': 0,
        'flag': None,
    }

    try:
        if action == 'check':
            # shetcode hanya mendaftarkan havoc(0), jadi varian dipatok 0
            # berapa pun nomor vuln yang dikirim ForcAD.
            tick = int(time.time())
            msg = dict(base, method='havoc', variantId=0,
                       currentRoundId=tick, relatedRoundId=tick,
                       taskChainId=f'havoc_{team_id}_{tick}')
            res = _post(base_url, msg, timeout_s)
            _quit(_status(res.get('result'), action), '', f"havoc: {res.get('message')}")

        if action == 'put':
            tick = int(time.time())
            chain = f'adlab_{team_id}_{vuln}_{tick}'
            msg = dict(base, method='putflag', variantId=vuln, flag=flag,
                       currentRoundId=tick, relatedRoundId=tick,
                       taskChainId=chain)
            res = _post(base_url, msg, timeout_s)
            code = _status(res.get('result'), action)
            if code != OK:
                _quit(code, '', f"putflag: {res.get('message')}")
            # chain + varian + ronde dititipkan ke GET lewat flag_id
            payload = json.dumps({'c': chain, 'v': vuln, 'r': tick},
                                 separators=(',', ':'))
            _quit(OK, payload, f'putflag chain={chain}')

        if action == 'get':
            raw = rest[0] if rest else ''
            try:
                saved = json.loads(raw)
                chain, variant, related = saved['c'], saved['v'], saved['r']
            except (ValueError, KeyError, TypeError):
                _quit(CHECKER_ERROR, '', f'flag_id tidak bisa dibaca: {raw!r}')
            msg = dict(base, method='getflag', variantId=variant, flag=flag,
                       currentRoundId=int(time.time()), relatedRoundId=related,
                       taskChainId=chain)
            res = _post(base_url, msg, timeout_s)
            _quit(_status(res.get('result'), action), '', f"getflag: {res.get('message')}")

        _quit(CHECKER_ERROR, '', f'aksi tidak dikenal: {action}')

    except SystemExit:
        raise
    except urllib.error.HTTPError as exc:
        # Dibedakan dari URLError: HTTPError berarti sidecar HIDUP tapi menolak
        # permintaan (mis. 422 validasi pydantic). Isi balasannya memuat field
        # mana yang salah — tanpa mencetaknya, pesan jadi menyesatkan.
        try:
            body = exc.read().decode()[:500]
        except Exception:
            body = '(gagal membaca body)'
        _quit(CHECKER_ERROR, '', f'sidecar menolak permintaan HTTP {exc.code}: {body}')
    except urllib.error.URLError as exc:
        # Sidecar tidak terjangkau = masalah infrastruktur KITA, bukan service
        # tim. Dibedakan dari DOWN supaya tidak menghukum tim.
        _quit(CHECKER_ERROR, '', f'sidecar checker tak terjangkau: {exc}')
    except Exception:
        _quit(CHECKER_ERROR, '', traceback.format_exc())
