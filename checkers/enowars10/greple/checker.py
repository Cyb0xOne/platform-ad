#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini, bukan child-nya. Cocok utk layout repo
# (checkers/enowars10/_lib + checkers/enowars10/greple/checker.py) MAUPUN
# layout di container celery ASALKAN _lib di-deploy SEKALI ke /checkers/_lib
# (dipakai bareng semua eno10_*), checker.py sendiri ke /checkers/eno10_greple/.
# JANGAN ikuti brief Step 3 apa adanya (docker cp _lib ke dalam
# eno10_greple/_lib) — itu menaruh _lib sebagai CHILD dan bikin
# ModuleNotFoundError: adlab_eno (sudah dicek di gate Task 2).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A
import re

PORT = 7777
# hash paste = SHA-224 (utils.Hash di source greple) -> 28 byte -> 56 hex char.
# Rute GET /p/{hex} di server hanya cocok kalau panjang hex-nya PAS 56;
# kalau tidak, jatuh ke 404 generik (ini yang dipakai gate "corrupt").
PASTE_ID_RE = re.compile(r"/p/([0-9a-f]{56})")

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        r = s.get("/")
        self.assert_eq(r.status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        # Body form asli servis: field "title" + "text" (BUKAN "content" —
        # dikoreksi dari respons nyata; "content" bikin postPastebin balas
        # error.InvalidRequest / 400). postPastebin sukses membalas redirect
        # 302 ke /p/{hex}, BUKAN 2xx dengan id di body (body redirect cuma
        # teks "moved" — id-nya hanya ada di header Location).
        r = s.post(
            "/pastebin",
            data={"title": A.rand_text(12), "text": flag},
            allow_redirects=False,
        )
        self.assert_eq(r.status_code, 302, "pastebin tolak simpan", Status.MUMBLE)
        loc = r.headers.get("Location", "")
        m = PASTE_ID_RE.search(loc)
        self.assert_(m is not None, "id paste tak ditemukan di Location", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(pid=m.group(1)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.get(f"/p/{st['pid']}")
        self.assert_eq(r.status_code, 200, "paste tak terambil", Status.CORRUPT)
        self.assert_in(flag, r.text, "flag tak ada di paste", Status.CORRUPT)
        self.cquit(Status.OK)

if __name__ == "__main__":
    try:
        c = Checker(sys.argv[2])
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
    except Exception as e:
        cquit(A.status_for(e), "checker error", repr(e))
