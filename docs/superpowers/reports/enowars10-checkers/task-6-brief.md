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

