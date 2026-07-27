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

