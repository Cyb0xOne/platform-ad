#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4 di greple/d3pl0y/flagdrive
# checker.py) — _lib SEKALI di /checkers/_lib, checker ini di
# /checkers/eno10_signmemaybe/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 1984

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        # /api/info (RootEndpoints.cs) — endpoint status ringan, tanpa auth.
        # Brief tak menyebut endpoint check secara eksplisit; dipakai ini
        # (bukan "/") krn baca source: mengembalikan JSON {service,status}
        # yg lebih pasti drpd berharap Razor "/" 200 (butuh wwwroot statis).
        r = s.get("/api/info")
        self.assert_eq(r.status_code, 200, "info down", Status.MUMBLE)
        self.assert_eq(r.json().get("status"), "online", "status bukan online", Status.MUMBLE)
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
        # Koreksi thd brief (dikonfirmasi baca ContractEndpoints.cs, bukan tebakan):
        # 1. CreateContract balas Results.Created(...) dgn anonymous object berisi
        #    {reference, ownerUsername, title, versionNumber, approvalState,
        #    checksum, archiveTicket} — TAK ADA field "id" sama sekali. Pengenal
        #    publik kontrak adalah "reference" (string spt "CNTR-<24 hex>"),
        #    bukan id numerik internal (yg tak pernah diekspos ke klien).
        # 2. Tak ada rute GET /api/contracts/{id} generik. Rute baca isi kontrak
        #    (dgn field "content") adalah GET /api/contracts/{reference}/versions/latest
        #    (lihat get() di bawah) — endpoint /api/contracts polos itu daftar
        #    kontrak MILIK SENDIRI (tanpa field content, cuma checksum).
        ref = r.json().get("reference")
        self.assert_(ref is not None, "reference kontrak kosong", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(t=tok, r=ref))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/api/contracts/{st['r']}/versions/latest", headers={"X-Session-Token": st['t']})
        self.assert_eq(r.status_code, 200, "kontrak tak terambil", Status.CORRUPT)
        # field "content" (content_text kolom DB, disalin verbatim dari PUT,
        # bukan echo dari request GET ini) — dicek via JSON key spesifik,
        # bukan r.text mentah, spy tak kebetulan cocok field lain (mis. pdfUrl).
        self.assert_in(flag, r.json().get("content", ""), "flag tak ada di kontrak", Status.CORRUPT)
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
