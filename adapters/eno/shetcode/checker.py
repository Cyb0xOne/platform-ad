#!/usr/bin/env python3
"""Checker format-ForcAD untuk service ENOWARS `shetcode`.

Tipis dengan sengaja: seluruh penerjemahan ada di `eno_adapter.py`.
Menambah service ENOWARS lain = salin direktori ini dan arahkan `base_url`
ke sidecar checker service tersebut.

Berbeda dengan adapter saarCTF/FAUST, di sini TIDAK ADA source checker yang
disalin — checker aslinya berjalan sebagai container HTTP tersendiri.

Tata letak saat di-deploy ke ForcAD (`/checkers/eno_shetcode/`):

    checker.py       <- file ini, harus executable
    eno_adapter.py   <- pustaka adapter

Sidecar yang harus hidup di network forcad_default:
    adlab-eno-shetcode  (enochecker3, port 8000)
    adlab-eno-mongo     (MongoDB, dipakai ChainDB)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eno_adapter import run  # noqa: E402

if __name__ == '__main__':
    run(base_url='http://adlab-eno-shetcode:8000', service_name='shetcode')
