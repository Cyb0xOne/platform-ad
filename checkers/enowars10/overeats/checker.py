#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4/5 di greple/d3pl0y/flagdrive/
# signmemaybe checker.py) — _lib SEKALI di /checkers/_lib, checker ini di
# /checkers/eno10_overeats/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 5432  # port eksternal nginx OverEats (BUKAN Postgres — Postgres-nya
             # cuma internal ke jaringan compose sendiri, tak pernah dipublish
             # ke luar; lihat brief & docker-compose.yml service ini).

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        # Koreksi thd brief (dikonfirmasi baca web/__init__.py, bukan tebakan):
        # dipakai /api/health (bukan "/" spt draft brief) — endpoint ini
        # benar2 menyentuh DB (db_query("SELECT 1")) sebelum balas 200
        # {"status":"healthy",...} atau 500 {"status":"unhealthy",...}, jadi
        # sinyal liveness yg lebih berarti drpd Jinja index.html statis yg
        # tak pernah menyentuh DB. Konsisten dgn preseden signmemaybe
        # (/api/info) & flagdrive (/api/health): dua assert (status code DAN
        # field JSON), bukan cuma status code mentah.
        r = s.get("/api/health")
        self.assert_eq(r.status_code, 200, "health down", Status.MUMBLE)
        self.assert_eq(r.json().get("status"), "healthy", "status bukan healthy", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        cu, cp = A.rand_username(), A.rand_password()
        self.assert_eq(s.post("/api/register", json={"username": cu, "password": cp}).status_code // 100, 2,
                       "register customer gagal", Status.MUMBLE)
        ctok = s.post("/api/login", json={"username": cu, "password": cp}).json().get("token")
        self.assert_(bool(ctok), "login customer gagal", Status.MUMBLE)
        ch = {"Authorization": f"Bearer {ctok}"}

        # Akun kedua HANYA alat bantu: place_order (di bawah) mewajibkan
        # restaurant_id yg valid (FK ke tabel restaurants — query eksplisit
        # "SELECT id FROM restaurants WHERE id = %s", 404 kalau tak ada), dan
        # init.sql tak menyemai satu restoran pun -> checker harus membuat
        # sendiri lewat akun ber-role "restaurant" (default register tanpa
        # "role" = "customer", persis di register(): data.get('role',
        # 'customer'); create_restaurant() balas 403 kalau bukan PERSIS role
        # restaurant).
        ru, rp = A.rand_username(), A.rand_password()
        self.assert_eq(
            s.post("/api/register", json={"username": ru, "password": rp, "role": "restaurant"}).status_code // 100,
            2, "register restoran gagal", Status.MUMBLE)
        rtok = s.post("/api/login", json={"username": ru, "password": rp}).json().get("token")
        self.assert_(bool(rtok), "login restoran gagal", Status.MUMBLE)
        rr = s.post("/api/restaurants", json={"name": A.rand_text(10), "cuisine": A.rand_text(6)},
                    headers={"Authorization": f"Bearer {rtok}"})
        self.assert_eq(rr.status_code // 100, 2, "buat restoran gagal", Status.MUMBLE)
        rest_id = rr.json().get("restaurant_id")
        self.assert_(rest_id is not None, "restaurant_id kosong", Status.MUMBLE)

        # Koreksi thd brief (dikonfirmasi baca web/__init__.py, BUKAN tebakan):
        # place_order() HANYA membaca restaurant_id/items/special_instructions
        # dari body -- field "note" yg dikirim brief langsung di request order
        # akan diam2 diabaikan (tak pernah disimpan). Flag disimpan lewat
        # endpoint TERPISAH: POST /api/orders/<id>/notes (create_note(),
        # baris 508-537) dgn body {"note": ...}, ke tabel order_notes yg
        # memang terpisah dari orders (dikonfirmasi jg di init.sql).
        orr = s.post("/api/orders", json={"restaurant_id": rest_id, "items": []}, headers=ch)
        self.assert_eq(orr.status_code // 100, 2, "buat order gagal", Status.MUMBLE)
        oid = orr.json().get("order_id")  # field balasan "order_id", BUKAN "id"
        self.assert_(oid is not None, "order_id kosong", Status.MUMBLE)

        nr = s.post(f"/api/orders/{oid}/notes", json={"note": flag}, headers=ch)
        self.assert_eq(nr.status_code // 100, 2, "buat note gagal", Status.MUMBLE)
        nid = nr.json().get("note_id")
        self.assert_(nid is not None, "note_id kosong", Status.MUMBLE)

        self.cquit(Status.OK, A.encode_state(t=ctok, o=str(oid), n=str(nid)))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)
        # Koreksi thd brief (dikonfirmasi baca web/__init__.py, BUKAN tebakan):
        # TIDAK ADA rute GET /api/orders/<id> generik sama sekali di service
        # ini (cuma /api/orders/<id>/details utk metadata order TANPA note,
        # dan /api/orders/<id>/notes utk notes) -- GET ke path draft brief
        # akan selalu 404. Rute yg benar balas LIST semua note order ini
        # ({"notes": [{"note_id","note","created_at"}, ...]}), bukan objek
        # tunggal, jadi harus dicari entry dgn note_id yg cocok state. Lapisan
        # crypto/notes_crypto.py: decrypt_note() mengembalikan None diam2
        # (entry difilter keluar dari list, bukan error) kalau expected_owner
        # (pemanggil) != owner asli yg tersimpan di ciphertext -- jadi WAJIB
        # pakai token customer yg SAMA dgn put(), bukan token lain yg cuma
        # "berhak" secara akses (restoran/driver akan dapat list kosong utk
        # note ini, diam2, walau order-nya sendiri bisa mereka lihat).
        r = s.get(f"/api/orders/{st['o']}/notes", headers={"Authorization": f"Bearer {st['t']}"})
        self.assert_eq(r.status_code, 200, "notes tak terambil", Status.CORRUPT)
        notes = r.json().get("notes", [])
        target = next((nt for nt in notes if str(nt.get("note_id")) == st['n']), None)
        self.assert_(target is not None, "note dgn note_id ini tak ditemukan", Status.CORRUPT)
        # Dicek lewat field JSON "note" yg sudah di-parse (hasil decrypt_note(),
        # disalin verbatim dari note_text saat PUT) -- bukan substring r.text
        # mentah, supaya tak kebetulan cocok field lain (mis. "created_at").
        self.assert_in(flag, target.get("note", ""), "flag tak ada di note", Status.CORRUPT)
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
