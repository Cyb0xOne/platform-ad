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

