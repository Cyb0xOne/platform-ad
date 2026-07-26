#!/usr/bin/env python3
import sys, base64
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini, bukan child-nya (lihat catatan Task 2 di
# checkers/enowars10/greple/checker.py). Layout server: _lib SEKALI di
# /checkers/_lib, checker ini di /checkers/eno10_d3pl0y/checker.py.
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
        # "/" di app.py cuma redirect 307 -> "/web/" (index landing.html, 200
        # tanpa sesi). requests mengikuti redirect utk GET secara default,
        # jadi status_code akhir yg dicek sudah otomatis 200 dari landing.html.
        self.assert_eq(s.get("/").status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, name = A.rand_username(), A.rand_text(8).replace(" ", "")
        # Koreksi thd brief (dikonfirmasi baca api.py & app.py, bukan tebakan):
        # 1. app.py: app.mount("/api", api) -> semua endpoint kontrak ada di
        #    prefix /api, BUKAN root ("/user/register" brief salah, harus
        #    "/api/user/register").
        # 2. api.py: register(username: Annotated[str, Form()] = "") -> body
        #    HARUS form-urlencoded (data=...), BUKAN json=... (json= akan bikin
        #    Form field kosong -> 422 dari FastAPI).
        r = s.post("/api/user/register", data={"username": u})
        self.assert_eq(r.status_code // 100, 2, "register gagal", Status.MUMBLE)
        # 3. api.py: return Response(content=token, status_code=201) -> body
        #    teks POLOS berisi token, BUKAN JSON {"token": ...} (brief salah
        #    asumsi r.json().get("token")). Pakai r.text apa adanya.
        token = r.text.strip()
        self.assert_(bool(token), "token kosong", Status.MUMBLE)
        r = s.put(f"/api/user/{u}/{name}", data=flag.encode(), headers=_basic(u, token))
        self.assert_eq(r.status_code // 100, 2, "put objek gagal", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(u=u, t=token, n=name))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/api/user/{st['u']}/{st['n']}", headers=_basic(st['u'], st['t']))
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
