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
    if isinstance(exc, (ConnectionError, TimeoutError, OSError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return Status.DOWN
    if isinstance(exc, (AssertionError, KeyError, ValueError, IndexError)):
        return Status.MUMBLE
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

