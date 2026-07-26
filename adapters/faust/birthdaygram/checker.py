#!/usr/bin/env python3
"""Checker format-ForcAD untuk service FAUST `birthdaygram`.

File ini sengaja tipis: seluruh penerjemahan ada di `faust_adapter.py`.
Menambah service FAUST lain = salin direktori ini, ganti `module`/`cls`,
dan taruh source checker aslinya di `svc/`.

Tata letak saat di-deploy ke ForcAD (`/checkers/faust_birthdaygram/`):

    checker.py            <- file ini, harus executable
    faust_adapter.py      <- pustaka adapter
    vendor/ctf_gameserver <- checkerlib yang di-vendor (jalan di Python 3.11)
    svc/template.py       <- checker asli birthdaygram, TIDAK diubah
    svc/utils.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faust_adapter import run  # noqa: E402


def _shim_stegano_bytes():
    """Terima `bytes` di `lsb.hide` — kompatibilitas versi, bukan perubahan perilaku.

    `template.py` mengirim flag sebagai bytes (`get_flag(tick).encode()`),
    sedangkan stegano 3.0.0 menuntut `str` dan mati dengan
        AttributeError: 'bytes' object has no attribute 'encode'
    Versi stegano yang dipakai FAUST tidak tercantum di repo service (folder
    checker/ tidak punya requirements.txt), jadi tidak bisa dipin ulang secara
    tepat. Shim ini hanya men-decode argumen, tidak mengubah data yang
    disembunyikan maupun gambar yang dihasilkan.

    Jalur ini hanya aktif pada `tick % 5 == 1` — 1 dari 5 ronde. Karena itu
    gate pertama LOLOS dan baru gagal di percobaan berikutnya; bukan perbedaan
    antar tim.
    """
    from stegano import lsb

    original = lsb.hide

    def hide(image, message, *args, **kwargs):
        if isinstance(message, bytes):
            message = message.decode('utf-8', 'surrogateescape')
        return original(image, message, *args, **kwargs)

    lsb.hide = hide


if __name__ == '__main__':
    _shim_stegano_bytes()
    # `utils.py` memakai CUR_DIR = "/tmp/" yang dipatok mati lalu menulis
    # gambar steganografi ke CUR_DIR + "/images/" dan CUR_DIR + "/flags/".
    # Berkasnya dibuat sendiri oleh checker; hanya DIREKTORI-nya yang
    # diasumsikan sudah ada. Runner FAUST menyiapkannya, ForcAD tidak.
    run(module='template', cls='TemplateChecker',
        scratch_dirs=('/tmp/flags', '/tmp/images'))
