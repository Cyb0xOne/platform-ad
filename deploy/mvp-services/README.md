# Service MVP lintas-framework

Tiga service A/D, **satu per framework checker**, ditambahkan ke game untuk variasi
kategori (bukan lagi 100% ENOWARS). Adapter checker-nya sudah ter-bake di image
celery ForcAD (`/checkers/`) dan attack path-nya terbukti di `docs/plan.md` Fase 1-2.

| Service | Framework | Kategori | Checker (di image celery) | Port di VM |
|---|---|---|---|---|
| shetcode | ENOWARS (enochecker3 + mongo) | web / PHP | `eno_shetcode/checker.py` | 8055 |
| birthdaygram | FAUST (checkerlib vendor) | web / Python | `faust_birthdaygram/checker.py` | 3000 |
| Licenser | saarCTF (gamelib + venv 3.12 + redis) | license / Python+C | `saar_licenser/checker.py` | 12935 |

## Deploy ke tiap VM tim

Compose ini dijalankan **di dalam VM vulnbox**, satu project per service:

```bash
cd /opt/adlab
docker compose -p shetcode     -f shetcode.yml     up -d   # butuh shetcode-db-init.sql di dir yang sama
docker compose -p birthdaygram -f birthdaygram.yml up -d
docker compose -p licenser     -f licenser.yml     up -d
```

Image (`adlab/shetcode`, `faust.cs.fau.de:5000/birthdaygram-webserver`,
`adlab/licenser`) dibangun sekali di host lalu disebar `docker save | ssh docker load`
— jalur virbr jauh lebih cepat daripada tiap VM menarik sendiri.

## Prasyarat sisi checker (di host, dekat celery)

- **shetcode** butuh sidecar enochecker3 + mongo di network `forcad_default`:
  compose project `adlab-eno` di `~/adlab/deploy` (`adlab-eno-shetcode`, `adlab-eno-mongo`).
- **Licenser** butuh venv `/opt/venv-saar` (Python 3.12) di image celery — dipilih
  lewat shebang checker, bukan `env_path`.
- **birthdaygram** butuh `checkerlib` ter-vendor di `/checkers/faust_birthdaygram/vendor`.

## Gate sebelum daftar (WAJIB)

Uji tiap checker dari dalam celery terhadap IP VM, harap exit 101 (OK) untuk
check/put/get sebelum menambahkannya ke `config.yml`:

```bash
docker exec forcad-celery-1 /checkers/<checker>/checker.py check <ip_vm>
ST=$(docker exec forcad-celery-1 /checkers/<checker>/checker.py put <ip_vm> <fid> <flag> <vuln>)
docker exec forcad-celery-1 /checkers/<checker>/checker.py get <ip_vm> "$ST" <flag> <vuln>
```

Flag berformat `[A-Z0-9]{31}=`. `put` mencetak state ke stdout yang jadi `flag_id` untuk `get`.

## Task di config.yml

Semua `checker_type` default (state privat, tak bocor ke scoreboard):

```yaml
- {name: shetcode,     checker: eno_shetcode/checker.py,      checker_type: "", puts: 1, gets: 1, places: 3, checker_timeout: 40}
- {name: birthdaygram, checker: faust_birthdaygram/checker.py, checker_type: "", puts: 1, gets: 1, places: 1, checker_timeout: 30}
- {name: Licenser,     checker: saar_licenser/checker.py,      checker_type: "", puts: 1, gets: 1, places: 1, checker_timeout: 20}
```

Port di atas juga harus masuk `SERVICE_PORTS` di `dashboard/backend/app.py` agar
modal service menampilkan `host:port` yang benar.

## Filler variasi kategori

Ditambahkan setelah 3 MVP untuk kategori yang belum ada:

| Service | Framework | Kategori | Port | Task |
|---|---|---|---|---|
| SaarLandCryptoGalore | saarCTF | crypto | 51349 | `cryptogalore` → `saar_slcg/checker.py` (places 1, timeout 20) |

Checker `saar_slcg`: pola sama seperti `saar_licenser` — salin adapter+gamelib,
taruh `svc/{interface.py,config.toml}` dari bank, ganti `cls` ke `SLCGInterface`.
Karena `/checkers` bind-mount dan depsnya (`pycryptodome`) sudah di venv-saar,
**tanpa rebuild image**. Service dibangun dari bank di host (`docker compose build`,
base `saarsec/saarctf-ci-base:trixie` sudah ada) lalu `docker save|load` ke VM.

### Catatan pwntools (penghambat kategori pwn/binary via saarCTF)

Service saarCTF berbasis **TCP tube** (Calendar, BlockRope, RCEaaS) checker-nya
memakai `gamelib.remote_connection`, yang meng-`import pwnlib` (pwntools).
venv-saar saat ini **belum** punya pwntools, dan venv itu di-bake (bukan mount),
sehingga menambah service pwn saarCTF menuntut:
1. tambah `pwntools` ke baris `uv pip install` di `docker_config/celery/Dockerfile.fast`,
2. **rebuild image celery** (pwntools menarik native deps unicorn/capstone).

Layer venv-saar terbukti resolve pwntools+unicorn ~55 dtk; kegagalan install live
hanya karena venv read-only bagi user non-root, jadi rebuild (konteks root) aman.
