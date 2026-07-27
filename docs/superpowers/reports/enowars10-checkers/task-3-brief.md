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

