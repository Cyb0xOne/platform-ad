#!/opt/venv-saar/bin/python3
"""Checker format-ForcAD untuk service saarCTF `SaarLandCryptoGalore` (crypto).

Pola identik saar_licenser (lihat ../licenser/checker.py): tipis, seluruh
penerjemahan ada di saar_adapter.py. Bedanya hanya kelas interface.

Deploy ke ForcAD (`/checkers/saar_slcg/`): checker.py (executable) +
saar_adapter.py + gamelib/ (disalin dari saar_licenser) + svc/interface.py +
svc/config.toml (dari bank saarctf-2025/SaarLandCryptoGalore/checkers/).

Deps: Crypto.Util.number -> pycryptodome, SUDAH ada di venv-saar, jadi tanpa
rebuild image (dir /checkers adalah bind-mount). Kontras dengan service saarCTF
berbasis TCP tube (Calendar/BlockRope/RCEaaS) yang butuh `pwntools` via
gamelib.remote_connection -> perlu bake ke venv-saar + rebuild image celery.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from saar_adapter import run  # noqa: E402

if __name__ == '__main__':
    run(module='interface', cls='SLCGInterface')
