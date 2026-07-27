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

