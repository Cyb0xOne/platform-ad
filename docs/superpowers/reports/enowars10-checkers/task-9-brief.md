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

