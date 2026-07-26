#!/opt/venv-saar/bin/python3
"""Checker format-ForcAD untuk service saarCTF `Licenser`.

SHEBANG BUKAN `/usr/bin/env python3` — DISENGAJA.
gamelib memakai f-string bergaya PEP 701 (kutip sama bersarang, mis.
`f"{d.get('k')}"`) yang baru sah di Python >= 3.12, sedangkan image celery
ForcAD adalah python:3.11 dan menaikkannya berisiko ke runtime engine.
ForcAD mengeksekusi berkas checker LANGSUNG sebagai proses, jadi shebang-lah
yang memilih interpreter. `/opt/venv-saar` dibuat di blok CUSTOMIZE pada
docker_config/celery/Dockerfile.fast (lihat deploy/fase1-saar.sh).
Inilah "virtualenv per adapter" yang disebut di docs/plan.md.

Tipis dengan sengaja: seluruh penerjemahan ada di `saar_adapter.py`.
Menambah service saarCTF lain = salin direktori ini, ganti `module`/`cls`,
taruh `interface.py` + `config.toml` aslinya di `svc/`.

Tata letak saat di-deploy ke ForcAD (`/checkers/saar_licenser/`):

    checker.py          <- file ini, harus executable
    saar_adapter.py     <- pustaka adapter
    gamelib/            <- gamelib asli, TIDAK diubah
    svc/interface.py    <- checker asli Licenser, TIDAK diubah
    svc/config.toml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from saar_adapter import run  # noqa: E402

if __name__ == '__main__':
    run(module='interface', cls='LicenserServiceInterface')
