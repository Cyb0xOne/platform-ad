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

