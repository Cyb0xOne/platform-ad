#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3 di greple/d3pl0y checker.py) —
# _lib SEKALI di /checkers/_lib, checker ini di /checkers/eno10_flagdrive/checker.py.
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
        # Koreksi thd brief (dikonfirmasi baca shared/src/lib.rs & backend/src/api_routes/files.rs,
        # BUKAN tebakan): enum FlagDriveFileVisibility tak punya #[serde(rename_all=...)] apa pun
        # -> representasi JSON-nya adalah nama varian Rust APA ADANYA ("Private", huruf besar di
        # depan), BUKAN "private" (brief salah tebak lowercase). "visibility" jg field WAJIB di
        # struct UploadMetadata (tak ada #[serde(default)] utknya) -> kalau nilainya tak cocok
        # varian manapun, seluruh parse JSON UploadMetadata gagal DIAM-DIAM (files.rs:
        # `if let Ok(payload) = serde_json::from_slice::<UploadMetadata>(&bytes) {...}`), sehingga
        # `token` lokal di handler tetap string kosong walau token yg dikirim valid -> upload_file
        # balas 400 "Token, name, and file content are required". frontend/src/components/
        # upload_modal.rs jg menggunakan label persis "Public"/"Following"/"Followers"/"Private"
        # (match arm huruf besar) utk field yg sama -> mengonfirmasi silang lewat consumer nyata.
        data = {"json": json.dumps({"token": token, "visibility": "Private"})}
        r = s.post("/api/file/upload", files=files, data=data)
        self.assert_eq(r.status_code // 100, 2, "upload gagal", Status.MUMBLE)
        fid = r.json().get("file_id") or r.json().get("id")
        self.assert_(fid is not None, "file_id kosong", Status.MUMBLE)
        self.cquit(Status.OK, A.encode_state(t=token, f=str(fid)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        r = s.post(f"/api/file/download/{st['f']}", json={"token": st['t']})
        self.assert_eq(r.status_code, 200, "download gagal", Status.CORRUPT)
        # Koreksi thd brief: respons sukses endpoint ini ber-content-type
        # application/octet-stream (byte file mentah, BUKAN teks/HTML spt greple/d3pl0y) —
        # dikonfirmasi di files.rs (`download_file`, header "content-type" ->
        # "application/octet-stream" pada Response sukses). Cek keberadaan flag di level byte
        # (r.content) drpd r.text supaya tak bergantung pada tebakan charset requests utk
        # content-type non-teks.
        self.assert_(flag.encode() in r.content, "flag tak ada di file", Status.CORRUPT)
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
