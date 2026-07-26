# Checker enowars10 (11 service) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menulis 11 checker checklib native dari nol sehingga ke-11 service `enowars10-2026` bisa di-check UP oleh ForcAD dan ikut permainan A/D.

**Architecture:** Tiap checker = file Python `checklib.BaseChecker`, drop-in ke `/checkers/` container celery ForcAD (jalur sama dengan blitz/omctf), bicara ke service via HTTP/TCP/telnet. Satu modul harness bersama `_lib/adlab_eno.py` memuat semua utilitas berulang. Nol adapter, nol sidecar.

**Tech Stack:** Python 3.11, `checklib==0.7.0` (sudah di image celery), `requests`, `pexpect`, stdlib `socket`/`imaplib`/`smtplib`. Uji harness dengan `pytest`. Gate checker dijalankan di dalam container celery terhadap service enowars10 yang berjalan.

## Global Constraints

Setiap task tunduk pada ini (nilai verbatim dari spec `docs/superpowers/specs/2026-07-27-enowars10-checkers-design.md`):

- **Format checker: checklib native.** `from checklib import *`, kelas `Checker(BaseChecker)`, entry `c = Checker(sys.argv[2]); c.action(sys.argv[1], *sys.argv[3:])`.
- **Exit code:** `Status.OK`=101, `Status.CORRUPT`=102, `Status.MUMBLE`=103, `Status.DOWN`=104, `Status.ERROR`=110. Keluar via `self.cquit(Status.X, public, private)`.
- **State PUT→GET lewat flag_id:** `put` memanggil `self.cquit(Status.OK, <state-string>)`; string itu jadi argumen `flag_id` di `get`. Encode kredensial sebagai JSON.
- **`checker_type: ''`** di config.yml (flag_id privat, tak tampil di scoreboard).
- **Shebang `#!/usr/bin/env python3`** (interpreter celery 3.11) kecuali sebuah service menuntut lib yang butuh Python lebih baru → venv-per-checker via shebang absolut (pola `docs/plan.md` §venv saarCTF). Uji dulu di 3.11.
- **`checkers/requirements.txt` DITAMBAH, tidak ditimpa.** Berkas dipakai bersama semua checker; menimpanya menghapus dependency checker lain (pelajaran Fase 1).
- **Dependency checker masuk lewat blok CUSTOMIZE `docker_config/celery/Dockerfile.fast` → rebuild image celery** (`control.py build --fast`, bukan cuma `start`).
- **Checker jalan sebagai `nobody`** di celery: hindari tulis ke path milik root; direktori kerja butuh mode permisif (pelajaran Fase 1 `/checkers/.state`).
- **Gate wajib sebelum daftar:** `check→101`, `put→101` (tangkap stdout=flag_id), `get→101`, plus `get` flag_id-asal-ngawur→102, `check` host mati→104. Dijalankan dari dalam container celery terhadap service yang berjalan.
- **Server:** SSH `reky@192.168.43.136`, PATH kosong di shell non-interaktif (set PATH eksplisit / `bash -lc`). Docker di `/usr/bin/docker`. VM tim `10.13.37.11`/`10.13.37.12`; untuk uji, service enowars10 bisa dijalankan di satu VM atau di host di network yang terjangkau celery.

---

## File Structure

```
checkers/enowars10/
  _lib/
    adlab_eno.py            # harness bersama — Task 1
    test_adlab_eno.py       # unit test harness — Task 1
  greple/checker.py         # Task 2  (template HTTP)
  d3pl0y/checker.py         # Task 3
  flagdrive/checker.py      # Task 4
  signmemaybe/checker.py    # Task 5
  overeats/checker.py       # Task 6
  funsplash/checker.py      # Task 7
  leet-date/checker.py      # Task 8
  superregister/checker.py  # Task 9  (TCP line)
  inbox/checker.py          # Task 10 (SMTP+IMAP)
  mediocre/checker.py       # Task 11 (spike telnet)
  enomoloch/checker.py      # Task 12 (spike Arkime)
deploy/
  enowars10-deploy.sh       # helper: build+jalankan satu service enowars10 untuk uji — Task 2
forcad/
  config.enowars10.yml      # entri task per checker — ditambah inkremental tiap task
```

Setiap `checker.py` di-deploy ke celery `/checkers/eno10_<svc>/checker.py` bersama salinan `_lib/`. Setiap task checker berakhir dengan gate lolos + commit; pendaftaran ke `config.yml` bagian dari task.

---

### Task 1: Harness bersama `_lib/adlab_eno.py`

Fungsi murni yang di-TDD sungguhan. Checker (Task 2+) mengkonsumsinya.

**Files:**
- Create: `checkers/enowars10/_lib/adlab_eno.py`
- Test: `checkers/enowars10/_lib/test_adlab_eno.py`

**Interfaces:**
- Produces:
  - `rand_username() -> str`, `rand_password() -> str`, `rand_text(n: int = 24) -> str`
  - `encode_state(**kw) -> str` — JSON kompak satu baris.
  - `decode_state(s: str) -> dict` — melempar `ValueError` bila tak terbaca.
  - `http(host: str, port: int, timeout: float = 10.0) -> requests.Session` — session dengan `base` attribute `f"http://{host}:{port}"` dan timeout default via adapter.
  - `LineClient(host, port, timeout=10.0)` — `.sendline(b)`, `.recv_until(delim: bytes) -> bytes`, `.recv(n) -> bytes`, `.close()`.
  - `status_for(exc: Exception)` — kembalikan `Status.DOWN` untuk error koneksi/timeout/OSError, `Status.MUMBLE` untuk `AssertionError/KeyError/ValueError/IndexError`, `Status.ERROR` selain itu.

- [ ] **Step 1: Tulis test yang gagal**

```python
# checkers/enowars10/_lib/test_adlab_eno.py
import adlab_eno as A
from checklib import Status

def test_state_roundtrip():
    s = A.encode_state(u="alice", p="pw123", rid="42")
    assert A.decode_state(s) == {"u": "alice", "p": "pw123", "rid": "42"}

def test_state_compact_single_line():
    assert "\n" not in A.encode_state(u="x")

def test_decode_bad_raises_valueerror():
    import pytest
    with pytest.raises(ValueError):
        A.decode_state("bukan json")

def test_rand_unique_enough():
    assert len({A.rand_username() for _ in range(200)}) > 190

def test_status_for_connection_error_is_down():
    assert A.status_for(ConnectionError()) == Status.DOWN
    assert A.status_for(TimeoutError()) == Status.DOWN
    assert A.status_for(OSError()) == Status.DOWN

def test_status_for_assertion_is_mumble():
    assert A.status_for(AssertionError()) == Status.MUMBLE
    assert A.status_for(KeyError()) == Status.MUMBLE

def test_http_session_has_base():
    s = A.http("1.2.3.4", 8000)
    assert s.base == "http://1.2.3.4:8000"
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `cd checkers/enowars10/_lib && pip install requests checklib pytest && pytest test_adlab_eno.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adlab_eno'`.

- [ ] **Step 3: Tulis implementasi minimal**

```python
# checkers/enowars10/_lib/adlab_eno.py
import json, random, socket, string
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from checklib import Status

_ADJ = ["Able", "Brave", "Calm", "Deft", "Eager", "Fair", "Glad", "Keen"]
_NOUN = ["Otter", "Falcon", "Cedar", "Quartz", "Maple", "Heron", "Comet"]

def rand_username():
    return random.choice(_ADJ) + random.choice(_NOUN) + str(random.randint(1000, 9999))

def rand_password():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))

def rand_text(n=24):
    return "".join(random.choices(string.ascii_letters + " ", k=n)).strip()

def encode_state(**kw):
    return json.dumps(kw, separators=(",", ":"))

def decode_state(s):
    d = json.loads(s)               # json.loads melempar ValueError untuk input tak sah
    if not isinstance(d, dict):
        raise ValueError("state bukan objek")
    return d

def http(host, port, timeout=10.0):
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504])
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.base = f"http://{host}:{port}"
    orig = s.request
    def _req(method, url, **kw):
        kw.setdefault("timeout", timeout)
        if url.startswith("/"):
            url = s.base + url
        return orig(method, url, **kw)
    s.request = _req
    return s

class LineClient:
    def __init__(self, host, port, timeout=10.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""
    def sendline(self, b):
        if isinstance(b, str): b = b.encode()
        self.s.sendall(b + b"\n")
    def recv_until(self, delim):
        while delim not in self.buf:
            chunk = self.s.recv(4096)
            if not chunk: break
            self.buf += chunk
        i = self.buf.find(delim)
        if i < 0:
            out, self.buf = self.buf, b""
            return out
        out = self.buf[:i + len(delim)]; self.buf = self.buf[i + len(delim):]
        return out
    def recv(self, n=4096):
        if self.buf:
            out, self.buf = self.buf[:n], self.buf[n:]; return out
        return self.s.recv(n)
    def close(self):
        try: self.s.close()
        except OSError: pass

def status_for(exc):
    # koneksi/timeout dulu — genuine DOWN (bukan ValueError, aman di atas)
    if isinstance(exc, (ConnectionError, TimeoutError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return Status.DOWN
    # service hidup tapi salah -> MUMBLE. requests.JSONDecodeError IS-A ValueError
    # (tertangkap di sini); requests.HTTPError bukan ValueError, jadi eksplisit.
    # PENTING: cek ini SEBELUM OSError — requests.RequestException subclass OSError,
    # jadi OSError-first akan salah mengklasifikasi HTTPError/JSONDecodeError jadi DOWN.
    if isinstance(exc, (AssertionError, KeyError, ValueError, IndexError,
                        requests.exceptions.HTTPError)):
        return Status.MUMBLE
    if isinstance(exc, OSError):        # sisa OSError = socket error asli -> DOWN
        return Status.DOWN
    return Status.ERROR
```

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `pytest test_adlab_eno.py -v`
Expected: PASS semua 7 test.

- [ ] **Step 5: Commit**

```bash
git add checkers/enowars10/_lib/adlab_eno.py checkers/enowars10/_lib/test_adlab_eno.py
git commit -m "feat(eno10): harness bersama _lib/adlab_eno.py + unit test"
```

---

### Task 2: Checker greple (:7777) — template HTTP

Service Zig; flag di pastebin. Ini template semua checker HTTP; task berikut mengikuti bentuk sama dengan kontrak endpoint berbeda.

**Files:**
- Create: `checkers/enowars10/greple/checker.py`
- Create: `deploy/enowars10-deploy.sh`
- Modify: `forcad/config.enowars10.yml` (buat, entri greple)

**Interfaces:**
- Consumes: `adlab_eno` (Task 1) — `http`, `rand_username`, `rand_password`, `rand_text`, `encode_state`, `decode_state`, `status_for`.
- Produces: pola `Checker(BaseChecker)` dengan `check/put/get`, entrypoint standar; dikonsumsi Task 3–12 sebagai bentuk acuan.

Kontrak endpoint (dari recon §7): `POST /pastebin` (form/JSON body memuat teks paste) → respons memuat id hex; `GET /p/{hex}` → teks paste. `POST /user_account` login bila perlu; pastebin bisa anonim.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A
import re

PORT = 7777

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        r = s.get("/")
        self.assert_eq(r.status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        r = s.post("/pastebin", data={"content": flag})
        self.assert_eq(r.status_code // 100, 2, "pastebin tolak simpan", Status.MUMBLE)
        m = re.search(r"/p/([0-9a-f]+)", r.text) or re.search(r"([0-9a-f]{8,})", r.text)
        self.assert_(m is not None, "id paste tak ditemukan", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(pid=m.group(1)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/p/{st['pid']}")
        self.assert_eq(r.status_code, 200, "paste tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di paste", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try (lihat catatan di checker lain) — c harus terikat
    # sebelum klausa except mereferensikannya. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Tulis helper deploy service (dipakai semua task berikut)**

```bash
# deploy/enowars10-deploy.sh — jalankan DI SERVER
# pemakaian: enowars10-deploy.sh <service-dir> [up|down]
#   contoh: enowars10-deploy.sh greple up   -> build+jalankan di host, di network forcad_default
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin
SVC="$1"; ACT="${2:-up}"
SRC="$HOME/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/$SVC"
# CATATAN: bank soal ada di laptop, bukan server. Untuk uji, rsync source service
# ke server lebih dulu: rsync -az <laptop>/$SVC reky@server:~/adlab/eno10/$SVC
WORK="$HOME/adlab/eno10/$SVC"
cd "$WORK"
if [ "$ACT" = "down" ]; then docker compose down -v; exit 0; fi
# sambungkan ke network yang sama dgn celery agar checker menjangkau via nama/IP
docker compose up -d --build
docker compose ps
```

Catat batasan di komentar: service enowars10 memakai network `default` sendiri; agar celery menjangkaunya, jalankan service dengan IP host yang terekspos (port publish) lalu gate memakai `host.docker.internal`/IP host, ATAU jalankan service di VM tim (10.13.37.x) seperti service Fase 1. Untuk uji cepat, publish port ke host dan gate pakai IP host server.

- [ ] **Step 3: Deploy service greple + jalankan gate**

Run (di server, service greple sudah berjalan di `<svc-ip>:7777`):
```bash
C=$(docker ps -qf name=forcad-celery | head -1)
# salin harness + checker ke container
docker exec $C mkdir -p /checkers/eno10_greple
docker cp checkers/enowars10/_lib $C:/checkers/eno10_greple/_lib
docker cp checkers/enowars10/greple/checker.py $C:/checkers/eno10_greple/checker.py
docker exec $C chmod +x /checkers/eno10_greple/checker.py
FLAG="ENOTESTFLAG$(date +%s)AAAAAAAAAAAA="
docker exec $C /checkers/eno10_greple/checker.py check <svc-ip>; echo "check=$?"
docker exec $C /checkers/eno10_greple/checker.py put <svc-ip> "" "$FLAG" 0 > /tmp/g.out; echo "put=$?"; FID=$(cat /tmp/g.out)
docker exec $C /checkers/eno10_greple/checker.py get <svc-ip> "$FID" "$FLAG" 0; echo "get=$?"
```
Expected: `check=101 put=101 get=101`, dan baris stdout put berbentuk `{"pid":"..."}`.

- [ ] **Step 4: Gate jalur gagal**

Run:
```bash
docker exec $C /checkers/eno10_greple/checker.py get <svc-ip> '{"pid":"deadbeef"}' "$FLAG" 0; echo "corrupt=$?"
docker exec $C /checkers/eno10_greple/checker.py check 10.13.37.99; echo "down=$?"
```
Expected: `corrupt=102`, `down=104`. Bila request shape meleset (mis. field body `content` salah nama), iterasi checker Step 1 terhadap respons nyata service sampai gate lolos.

- [ ] **Step 5: Daftarkan di config + verifikasi engine**

```yaml
# forcad/config.enowars10.yml — tambahkan ke tasks:
  - name: greple
    checker: eno10_greple/checker.py
    checker_type: ''
    checker_timeout: 20
    puts: 1
    gets: 1
    places: 1
```
Terapkan config (reset+clean+setup+start seperti `deploy/fase05-cutover.sh`), tunggu 1 ronde, konfirmasi log celery `Finished testing … task <greple> … CHECK UP; PUT UP; GET UP`.

- [ ] **Step 6: Commit**

```bash
git add checkers/enowars10/greple/checker.py deploy/enowars10-deploy.sh forcad/config.enowars10.yml
git commit -m "feat(eno10): checker greple (pastebin) + gate lolos"
```

---

### Task 3: Checker d3pl0y (:2553) — object store, Basic auth

**Files:** Create `checkers/enowars10/d3pl0y/checker.py`; Modify `forcad/config.enowars10.yml`.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §4): `POST /user/register` (username) → token; `PUT /user/{owner}/{name}` body=bytes objek, header `Authorization: Basic base64(user:token)` → simpan; `GET /user/{owner}/{name}` → bytes.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys, base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 2553

def _basic(u, t):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{t}".encode()).decode()}

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_eq(s.get("/").status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, name = A.rand_username(), A.rand_text(8).replace(" ", "")
        r = s.post("/user/register", json={"username": u})
        self.assert_eq(r.status_code // 100, 2, "register gagal", Status.MUMBLE)
        token = r.json().get("token")
        self.assert_(bool(token), "token kosong", Status.MUMBLE)
        r = s.put(f"/user/{u}/{name}", data=flag.encode(), headers=_basic(u, token))
        self.assert_eq(r.status_code // 100, 2, "put objek gagal", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(u=u, t=token, n=name))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/user/{st['u']}/{st['n']}", headers=_basic(st['u'], st['t']))
        self.assert_eq(r.status_code, 200, "objek tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di objek", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy service d3pl0y, jalankan gate 3-langkah** (pola Task 2 Step 3), konfirmasi `check=101 put=101 get=101`. Iterasi request shape (nama field register/token, path objek) terhadap respons nyata bila meleset.
- [ ] **Step 3: Gate jalur gagal** (Task 2 Step 4): flag_id ngawur→102, host mati→104.
- [ ] **Step 4: Daftarkan di config.enowars10.yml** (`name: d3pl0y`, `checker: eno10_d3pl0y/checker.py`, sisanya seperti greple), verifikasi 1 ronde `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker d3pl0y (object store) + gate lolos`.

---

### Task 4: Checker flagdrive (:4859) — file store, token multipart

**Files:** Create `checkers/enowars10/flagdrive/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §5): `POST /api/auth/register` `{username,password}`; `POST /api/auth/login` → token; `POST /api/file/upload` multipart `file=<bytes>` + `json={"token":..,"visibility":"private"}`; `POST /api/file/download/{id}` JSON `{"token":..}` → bytes.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A
import io, json

PORT = 4859

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_eq(s.get("/api/health").status_code, 200, "health down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, p = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/api/auth/register", json={"username": u, "password": p}).status_code // 100, 2,
                       "register gagal", Status.MUMBLE)
        r = s.post("/api/auth/login", json={"username": u, "password": p})
        token = r.json().get("token")
        self.assert_(bool(token), "login gagal", Status.MUMBLE)
        files = {"file": ("f.txt", io.BytesIO(flag.encode()))}
        data = {"json": json.dumps({"token": token, "visibility": "private"})}
        r = s.post("/api/file/upload", files=files, data=data)
        self.assert_eq(r.status_code // 100, 2, "upload gagal", Status.MUMBLE)
        fid = r.json().get("file_id") or r.json().get("id")
        self.assert_(bool(fid), "file_id kosong", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(t=token, f=str(fid)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.post(f"/api/file/download/{st['f']}", json={"token": st['t']})
        self.assert_eq(r.status_code, 200, "download gagal", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di file", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy + gate 3-langkah** (konfirmasi nama field `file_id`/`token`/visibility terhadap respons nyata; auth flagdrive di-obfuscate di kode Rust tapi jalur praktis = token dari JSON body).
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: flagdrive`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker flagdrive (file store) + gate lolos`.

---

### Task 5: Checker signmemaybe (:1984) — contracts, X-Session-Token

**Files:** Create `checkers/enowars10/signmemaybe/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §3): `POST /api/register` `{username,password}`; `POST /api/login` → token; header `X-Session-Token: <token>`; `POST /api/contracts` `{content:<flag>...}` → id; `GET /api/contracts/{id}` → content.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 1984

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_(s.get("/").status_code < 500, "server error", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, p = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/api/register", json={"username": u, "password": p}).status_code // 100, 2,
                       "register gagal", Status.MUMBLE)
        tok = s.post("/api/login", json={"username": u, "password": p}).json().get("token")
        self.assert_(bool(tok), "login gagal", Status.MUMBLE)
        h = {"X-Session-Token": tok}
        r = s.post("/api/contracts", json={"title": A.rand_text(8), "content": flag}, headers=h)
        self.assert_eq(r.status_code // 100, 2, "buat kontrak gagal", Status.MUMBLE)
        cid = r.json().get("id")
        self.assert_(cid is not None, "id kontrak kosong", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(t=tok, c=str(cid)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/api/contracts/{st['c']}", headers={"X-Session-Token": st['t']})
        self.assert_eq(r.status_code, 200, "kontrak tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di kontrak", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy + gate 3-langkah** (service .NET; build bisa lambat — anggarkan waktu).
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: signmemaybe`, `checker_timeout: 25`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker signmemaybe (contracts) + gate lolos`.

---

### Task 6: Checker overeats (:5432) — order note, Bearer

**Files:** Create `checkers/enowars10/overeats/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §2): `POST /api/register`/`/api/login` → `Authorization: Bearer <token>`; buat order lalu tambah order-note berisi flag (endpoint order/notes), atau chat message. Konfirmasi path note terhadap `init.sql` (`order_notes`) dan `web/__init__.py` saat implementasi.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 5432  # nginx eksternal OverEats

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_(s.get("/").status_code < 500, "server error", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, p = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/api/register", json={"username": u, "password": p}).status_code // 100, 2,
                       "register gagal", Status.MUMBLE)
        tok = s.post("/api/login", json={"username": u, "password": p}).json().get("token")
        self.assert_(bool(tok), "login gagal", Status.MUMBLE)
        h = {"Authorization": f"Bearer {tok}"}
        # Resource pembawa flag = order note. Endpoint/field dikonfirmasi terhadap
        # web/__init__.py saat Step 2; struktur di bawah adalah titik-awal.
        r = s.post("/api/orders", json={"items": [], "note": flag}, headers=h)
        self.assert_eq(r.status_code // 100, 2, "buat order/note gagal", Status.MUMBLE)
        oid = r.json().get("id") or r.json().get("order_id")
        self.assert_(oid is not None, "id order kosong", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(t=tok, o=str(oid)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        h = {"Authorization": f"Bearer {st['t']}"}
        r = s.get(f"/api/orders/{st['o']}", headers=h)
        self.assert_eq(r.status_code, 200, "order tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di note", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy (5 container: nginx/web/livetrack/postgres/cleanup) + gate 3-langkah** — konfirmasi endpoint order/note & nama field terhadap `web/__init__.py`; iterasi request body sampai `101/101/101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: overeats`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker overeats (order note) + gate lolos`.

---

### Task 7: Checker funsplash (:1337) — foto/koleksi, body ≤1000 B

**Files:** Create `checkers/enowars10/funsplash/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §6): `POST /napi/join`, `/napi/login` (cookie session); `/napi/upload` atau `/napi/collections` untuk membuat resource dengan deskripsi memuat flag; baca via `GET /napi/photos/{id}` atau `/napi/collections/{id}`. **Batas body 1000 B** — jaga payload kecil (flag 31 B aman).

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 1337

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_eq(s.get("/").status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)  # cookie session tersimpan otomatis di session
        u, p = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/napi/join", json={"username": u, "password": p}).status_code // 100, 2,
                       "join gagal", Status.MUMBLE)
        # Batas body 1000 B — payload kecil. Koleksi dgn deskripsi=flag.
        r = s.post("/napi/collections", json={"title": A.rand_text(8), "description": flag})
        self.assert_eq(r.status_code // 100, 2, "buat koleksi gagal", Status.MUMBLE)
        m = re.search(r'"(?:id|public_id)"\s*:\s*"?([A-Za-z0-9_-]+)', r.text)
        self.assert_(m is not None, "id koleksi tak ditemukan", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(u=u, p=p, cid=m.group(1)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        s.post("/napi/login", json={"username": st['u'], "password": st['p']})
        r = s.get(f"/napi/collections/{st['cid']}")
        self.assert_eq(r.status_code, 200, "koleksi tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di koleksi", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy (Gleam+Postgres18) + gate 3-langkah** — build Gleam bisa menabrak masalah seperti shetcode (anggarkan); konfirmasi route/field terhadap `server/src/server/router.gleam`, iterasi sampai `101/101/101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: funsplash`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker funsplash (foto/koleksi) + gate lolos`.

---

### Task 8: Checker leet-date (:6789) — profil bio, cookie session

**Files:** Create `checkers/enowars10/leet-date/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §9): `POST /api/register`, `/api/login` (cookie); `PATCH /api/me` set bio berisi flag; `GET /api/users/{handle}` atau `/api/me` baca bio. Alternatif: kirim pesan via `/api/conversations`.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 6789

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        self.assert_(s.get("/").status_code < 500, "server error", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)  # cookie session
        u, p = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/api/register", json={"handle": u, "password": p}).status_code // 100, 2,
                       "register gagal", Status.MUMBLE)
        self.assert_eq(s.post("/api/login", json={"handle": u, "password": p}).status_code // 100, 2,
                       "login gagal", Status.MUMBLE)
        # Flag di bio profil. Field dikonfirmasi terhadap router.go saat Step 2.
        r = s.patch("/api/me", json={"bio": flag})
        self.assert_eq(r.status_code // 100, 2, "set bio gagal", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(h=u, p=p))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/api/users/{st['h']}")
        self.assert_eq(r.status_code, 200, "profil tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di bio", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy (6 container) + gate 3-langkah** — konfirmasi field bio/handle terhadap `src/internal/handlers/router.go`, iterasi sampai `101/101/101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: leet-date`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker leet-date (profil bio) + gate lolos`.

---

### Task 9: Checker superregister (:6767) — protokol CLI TCP

**Files:** Create `checkers/enowars10/superregister/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno` — `LineClient`. Kontrak (recon §11): banner `=== SUPERREGISTER ...`; `Register <user> <pass>`; `Login <user> <pass>`; `AddVehicle` (interaktif, memuat note); `ReadNote <VehicleID> <NoteID>`. Prompt baris demi baris.

- [ ] **Step 1: Tulis checker** memakai `A.LineClient(host, 6767)`: `put` connect→recv banner→`Register`→`AddVehicle` dengan note=flag→tangkap Vehicle ID & Note ID dari respons→state simpan {u,p,vid,nid}; `get` connect→`Login`→`ReadNote vid nid`→assert flag di respons. Pakai `recv_until(b"\n")`/prompt-string. Konfirmasi urutan prompt `AddVehicle` terhadap `strings bin/SuperRegister`/interaksi nyata.

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 6767

class Checker(BaseChecker):
    def check(self):
        c = A.LineClient(self.host, PORT)
        banner = c.recv(256); c.close()
        self.assert_in(b"SUPERREGISTER", banner, "banner salah", Status.MUMBLE)
        self.cquit(Status.OK)
    def put(self, flag_id, flag, vuln):
        # Urutan prompt AddVehicle dikonfirmasi terhadap service; kerangka:
        c = A.LineClient(self.host, PORT); c.recv(256)
        u, p = A.rand_username(), A.rand_password()
        c.sendline(f"Register {u} {p}"); c.recv(256)
        c.sendline(f"Login {u} {p}"); c.recv(256)
        c.sendline("AddVehicle")
        # ... jawab prompt (plat, model, note=flag) sesuai interaksi nyata ...
        out = c.recv(512)
        vid, nid = self._parse_ids(out)   # ekstrak dari respons
        c.close()
        self.assert_(vid is not None, "id kendaraan tak diperoleh", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(u=u, p=p, v=vid, n=nid))
    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        c = A.LineClient(self.host, PORT); c.recv(256)
        c.sendline(f"Login {st['u']} {st['p']}"); c.recv(256)
        c.sendline(f"ReadNote {st['v']} {st['n']}")
        out = c.recv(512); c.close()
        self.assert_in(flag.encode(), out, "flag tak ada di note", Status.CORRUPT)
        self.cquit(Status.OK)
    def _parse_ids(self, out):
        import re
        vids = re.findall(rb"[Vv]ehicle\s*(?:ID)?\s*[:#]?\s*(\d+)", out)
        nids = re.findall(rb"[Nn]ote\s*(?:ID)?\s*[:#]?\s*(\d+)", out)
        return (vids[0].decode() if vids else None, nids[0].decode() if nids else "0")

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```

- [ ] **Step 2: Deploy + gate 3-langkah** — iterasi urutan prompt `AddVehicle` & regex `_parse_ids` terhadap interaksi nyata sampai `put=101 get=101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: superregister`, `checker_timeout: 20`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker superregister (CLI TCP) + gate lolos`.

---

### Task 10: Checker inbox (:4321 SMTP / :1234 IMAP)

**Files:** Create `checkers/enowars10/inbox/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §8): SMTP `AUTH PLAIN` di :4321; IMAP LOGIN di :1234. Implementasi custom — coba stdlib `smtplib`/`imaplib` dulu; bila handshake tak standar, turun ke `A.LineClient` protokol manual.

- [ ] **Step 1: Tulis checker** (mulai dari stdlib; siapkan fallback `A.LineClient` bila server custom menolak greeting `smtplib`/`imaplib`)

```python
#!/usr/bin/env python3
import sys, smtplib, imaplib, email
from email.message import EmailMessage
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

SMTP_PORT, IMAP_PORT = 4321, 1234

class Checker(BaseChecker):
    def check(self):
        try:
            c = A.LineClient(self.host, IMAP_PORT); g = c.recv(128); c.close()
            self.assert_in(b"OK", g, "greeting IMAP salah", Status.MUMBLE)
        except Exception as e:
            self.cquit(A.status_for(e), "imap down")
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        # Registrasi user dikonfirmasi terhadap internal/session/commands.go saat
        # Step 2 (auto-create saat LOGIN vs endpoint daftar). Titik-awal: SMTP
        # AUTH PLAIN lalu kirim ke mailbox user yg sama.
        u, p = A.rand_username().lower(), A.rand_password()
        sm = smtplib.SMTP(self.host, SMTP_PORT, timeout=10)
        try:
            sm.ehlo()
            sm.login(u, p)                       # AUTH PLAIN
            msg = EmailMessage(); msg["From"] = f"{u}@inbox"; msg["To"] = f"{u}@inbox"
            msg["Subject"] = A.rand_text(6); msg.set_content(flag)
            sm.send_message(msg)
        finally:
            sm.quit()
        self.cquit(Status.OK, A.encode_state(u=u, p=p))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        im = imaplib.IMAP4(self.host, IMAP_PORT)
        try:
            im.login(st['u'], st['p']); im.select("INBOX")
            _, ids = im.search(None, "ALL")
            found = False
            for num in ids[0].split():
                _, data = im.fetch(num, "(RFC822)")
                if flag.encode() in (data[0][1] or b""):
                    found = True; break
            self.assert_(found, "flag tak ada di mailbox", Status.CORRUPT)
        finally:
            im.logout()
        self.cquit(Status.OK)

if __name__ == "__main__":
    # KONSTRUKSI DI LUAR try — kalau di dalam, dan Checker() raise, klausa
    # `except c.get_check_finished_exception()` mereferensikan c yang unbound
    # -> NameError lolos dari jaring `except Exception`. Cocok dgn upstream ForcAD.
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
```
- [ ] **Step 2: Deploy (Go IMAP/SMTP) + gate 3-langkah** — tentukan cara registrasi user (recon: LOGIN di IMAP commands; mungkin auto-create). Iterasi sampai `101/101/101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: inbox`, `checker_timeout: 25`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker inbox (SMTP+IMAP) + gate lolos`.

---

### Task 11: SPIKE Checker mediocre (:1980) — telnet DSM-11

**Best-effort (spec §Risiko).** Bila buntu setelah usaha wajar, dokumentasikan & lanjut; tidak memblokir Task 1–10/12.

**Files:** Create `checkers/enowars10/mediocre/checker.py`; Modify config (hanya bila gate lolos).
**Interfaces:** Consumes `adlab_eno` — `expect_session` (pexpect). Kontrak (recon §10): haproxy :1980 → DSM-11 via terminal; login `MGR` (`DO_NOT_TOUCH_THIS.md`), prompt telnet.

- [ ] **Step 1: Spike interaktif** — sambungkan `telnet <ip> 1980` manual, petakan urutan login DSM-11 + perintah menyimpan/membaca sebuah global/record MUMPS. Catat transcript.
- [ ] **Step 2: Tulis checker** dengan `pexpect` (tambah `pexpect` ke `checkers/requirements.txt`) mengikuti transcript: `put` login→simpan flag di record→state simpan kunci record; `get` login→baca record→assert flag.
- [ ] **Step 3: Gate 3-langkah + jalur gagal**. Bila lolos, daftar config (`name: mediocre`, `checker_timeout: 40`) + verifikasi `UP`. Bila buntu: tulis `checkers/enowars10/mediocre/BLOCKED.md` berisi transcript + hambatan.
- [ ] **Step 4: Commit** `feat(eno10): checker mediocre (DSM-11)` atau `docs(eno10): mediocre spike terblok — transcript`.

---

### Task 12: SPIKE Checker enomoloch (:8005) — pcap + Arkime API

**Best-effort (spec §Risiko).** Aturan sama dengan Task 11.

**Files:** Create `checkers/enowars10/enomoloch/checker.py`; Modify config (hanya bila gate lolos).
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §1): Arkime :8005 (auth Arkime), volume `/pcaps` sebagai jalur ingest.

- [ ] **Step 1: Spike** — tentukan cara flag masuk: (a) tulis pcap berisi paket dengan flag di payload ke volume `/pcaps` (butuh akses volume — mungkin via container helper), lalu (b) query Arkime API/Elasticsearch untuk sesi berisi flag. Petakan auth Arkime (digest) & endpoint query.
- [ ] **Step 2: Tulis checker** — `put`: susun pcap minimal (mis. `scapy`/tulis byte pcap mentah) berisi flag, tempatkan di jalur ingest; state simpan penanda unik; `get`: query Arkime sessions API untuk penanda, assert flag. Tambah dependency (mis. `scapy`) ke requirements bila perlu.
- [ ] **Step 3: Gate 3-langkah + jalur gagal**. Lolos → daftar config (`name: enomoloch`, `checker_timeout: 40`) + verifikasi `UP`. Buntu → `checkers/enowars10/enomoloch/BLOCKED.md`.
- [ ] **Step 4: Commit** `feat(eno10): checker enomoloch (Arkime)` atau `docs(eno10): enomoloch spike terblok`.

---

## Catatan eksekusi lintas-task

- **Dependency image celery:** bila sebuah checker menambah dependency (`pexpect`, `scapy`), tambahkan ke `checkers/requirements.txt` (JANGAN timpa) lalu `control.py build --fast` + `start --fast`. Iterasi cepat tanpa rebuild: `docker cp` checker.py ke container jalan (seperti Task 2 Step 3) — tapi dependency baru tetap butuh rebuild.
- **Menjangkau service dari celery:** service enowars10 dijalankan di VM tim (`10.13.37.x`, jalur nftables Fase 0.5 sudah terbuka) atau di host dengan port publish (gate pakai IP host `192.168.43.136`). Pilih per service sesuai berat; `mediocre` (11 container) sebaiknya di VM/host tersendiri.
- **Config final:** setelah beberapa checker lolos, gabungkan entri ke `config.yml` aktif dan jalankan reset+clean+setup+start (pola `deploy/fase05-cutover.sh`, ingat `sudo rm -rf docker_volumes`).

## Verifikasi akhir (dari spec §Verifikasi)

1. Tiap checker Tier 1–2: gate 101·101·101 + 102 + 104 lolos terhadap service berjalan.
2. Terdaftar di config, ronde penuh `CHECK UP · PUT UP · GET UP` kedua tim.
3. Dashboard menampilkan service baru di grid.
4. Tier 3: bila spike buntu, `BLOCKED.md` terdokumentasi; 9 checker Tier 1–2 tetap lolos #1–3.
