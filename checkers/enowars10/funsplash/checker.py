#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4/5/6 di greple/d3pl0y/
# flagdrive/signmemaybe/overeats checker.py) — _lib SEKALI di /checkers/_lib,
# checker ini di /checkers/eno10_funsplash/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 1337

# Koreksi menyeluruh thd brief (dikonfirmasi baca router.gleam +
# web/auth.gleam + web/collection.gleam + shared/shared_*.gleam, LALU
# diverifikasi lagi via curl langsung ke instance live — bukan tebakan):
#
# 1. Body BUKAN JSON. auth.login()/auth.sign_up()/collection.create() semua
#    pakai `wisp.require_form(request)` (auth.gleam:57,109; collection.gleam:
#    96) — field form (shared_login.gleam, shared_signup.gleam,
#    shared_collection.gleam) hanya dibaca dari x-www-form-urlencoded/
#    multipart, BUKAN dari body JSON spt draft brief (`json={...}`). Checker
#    ini pakai `data={...}` (requests otomatis set Content-Type yg benar).
#
# 2. sign_up butuh field ekstra WAJIB "first_name" (shared_signup.gleam:45-48,
#    form.check_not_empty) yg tak disebut brief sama sekali — tanpanya form
#    gagal divalidasi (redirect ke /?error=..., bukan sukses). "last_name",
#    "bio", "available_for_hire" optional/checkbox, aman diabaikan (formal
#    v3.0.1 form.gleam: parse_checkbox atas field yg SAMA SEKALI tak ada di
#    values -> `[] -> False`, bukan error).
#
# 3. Respons join/login/create-collection BUKAN JSON berisi field id — semua
#    balas `wisp.redirect(...)` (redirect 303, dikonfirmasi live: `curl -i`
#    balas "303 See Other"). auth.gleam:87 login sukses -> redirect "/" +
#    Set-Cookie (uid,uname signed); auth.gleam:139 join sukses -> redirect
#    "/?registered=true" + Set-Cookie yg SAMA (sign_up auto-login).
#    collection.gleam:131-136 create sukses -> redirect ke
#    "/collections/" <> public_id (tanpa `redirect_to` custom). Jadi:
#    - id koleksi diambil dari HEADER `Location` (bukan body JSON/regex),
#      dgn allow_redirects=False supaya tak ikut lompat ke halaman index.
#    - sukses join/login TIDAK bisa disimpulkan dari status akhir stlh
#      redirect diikuti (baik sukses maupun gagal sama2 berakhir di rute GET
#      "/" atau "/login" yg SAMA2 dilayani wisp.not_found()-fallback
#      `serve_index` -> 200 index.html statis) — makanya dibuktikan via
#      GET /napi/me (auth.gleam:40-47, wisp_response 200 hanya kalau
#      context.user Some, balas JSON {"username":...}) tiap kali stlh
#      join/login, BUKAN dari status code redirect itu sendiri.
#
# 4. Field pengenal publik koleksi adalah "public_id" (models/collection.
#    gleam:11-23 `PublicId = String`; shared_collection.gleam:20-32
#    `collection_to_json` memancarkan key "public_id"), BUKAN "id" — sesuai
#    alternatif kedua yg disebut brief, dikonfirmasi bukan yg pertama.
#
# 5. collection.get() (web/collection.gleam:69-90, rute GET
#    /napi/collections/{id}) TIDAK mewajibkan login sama sekali (tak ada
#    `auth.require_login`, tak ada pengecekan field `private`) — dikonfirmasi
#    live, `curl` tanpa cookie tetap balas 200 + body lengkap. Ini PERSIS
#    kenapa catatan tugas menekankan: login di get() WAJIB dibuktikan lewat
#    /napi/me, bukan diasumsikan dari sukses-nya request login — kalau login
#    diam2 gagal, GET koleksi (yg publik dibuat private=False) tetap akan
#    200 dgn flag di dalamnya, jadi false-OK kalau assert login dilewati.
#    Kegagalan login diklasifikasi MUMBLE (bukan CORRUPT): servis hidup tapi
#    autentikasi tak berfungsi, bukan flag yg hilang/rusak.


def _redirect_location(resp):
    return resp.headers.get("Location", resp.headers.get("location", ""))


def _sync_cookie_header(s):
    # Ditemukan cuma lewat live testing (bukan statis dari source): wisp's
    # set_cookie (wisp v2.2.2, fungsi set_cookie di wisp.gleam) menandai
    # SEMUA cookie sesi (uid/uname, auth.gleam:94-104) sbg `Secure` KECUALI
    # request.host PERSIS "localhost"/"127.0.0.1"/"[::1]" DAN skema http DAN
    # tanpa header x-forwarded-proto. ForcAD tak pernah memanggil via
    # "localhost" (selalu IP container/VM) -> Set-Cookie SELALU ber-flag
    # Secure di jalur nyata manapun. requests.Session (dipakai A.http, murni
    # http://) taat RFC 6265 §4.1.2.5: cookie ber-flag Secure TAK PERNAH
    # dilampirkan balik ke request non-https, bahkan ke host yg SAMA persis
    # yg menerbitkannya — dikonfirmasi lewat instance live: replace kebijakan
    # cookiejar (`secure_protocols`) TIDAK mengubah perilaku ini (dicoba,
    # tetap gagal), tapi menyalin nilai cookie scr manual ke header `Cookie`
    # (di bawah) terbukti bekerja. ini bukan workaround "melewati keamanan" —
    # kita cuma meneruskan nilai yg server SENDIRI baru kasih ke kita, balik
    # ke server yg SAMA lewat jalur yg SAMA (server sendiri yg menganggap
    # jalur ini aman, krn dialah yg menerbitkan cookie ini di atasnya).
    # Tanpa ini: /napi/me & /napi/collections (POST) selalu tampak anonim
    # stlh join/login "sukses" — persis skenario false-negative yg diingatkan
    # di brief soal /napi/me.
    s.headers["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in s.cookies)


class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        # Tak ada endpoint health/info JSON di router.gleam (sudah dibaca
        # penuh) — "/" cuma menyajikan index.html statis (serve_index()),
        # konsisten dgn preseden d3pl0y/greple checker.py utk servis tanpa
        # rute health tersendiri.
        self.assert_eq(s.get("/").status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, p, fname = A.rand_username(), A.rand_password(), A.rand_username()

        r = s.post(
            "/napi/join",
            data={"username": u, "password": p, "first_name": fname},
            allow_redirects=False,
        )
        self.assert_(300 <= r.status_code < 400, "join gagal (bukan redirect)", Status.MUMBLE)
        _sync_cookie_header(s)

        me = s.get("/napi/me", allow_redirects=False)
        self.assert_eq(me.status_code, 200, "join gagal (sesi tak valid)", Status.MUMBLE)
        self.assert_eq(me.json().get("username"), u, "sesi user salah stlh join", Status.MUMBLE)

        r = s.post(
            "/napi/collections",
            data={"name": A.rand_username(), "description": flag},
            allow_redirects=False,
        )
        self.assert_(300 <= r.status_code < 400, "buat koleksi gagal (bukan redirect)", Status.MUMBLE)
        loc = _redirect_location(r)
        self.assert_(loc.startswith("/collections/"), f"buat koleksi gagal (redirect={loc!r})", Status.MUMBLE)
        cid = loc.rsplit("/", 1)[-1]
        self.assert_(bool(cid), "id koleksi kosong", Status.MUMBLE)

        self.cquit(Status.OK, A.encode_state(u=u, p=p, cid=cid))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)

        r = s.post(
            "/napi/login",
            data={"username": st["u"], "password": st["p"]},
            allow_redirects=False,
        )
        self.assert_(300 <= r.status_code < 400, "login gagal (bukan redirect)", Status.MUMBLE)
        _sync_cookie_header(s)

        # Bukti login benar2 berhasil (bukan cuma "request login tak error")
        # — lihat catatan #5/#3 di atas. Kegagalan di sini = MUMBLE, karena
        # ini soal autentikasi servis, bukan flag yg hilang/berubah.
        me = s.get("/napi/me", allow_redirects=False)
        self.assert_eq(me.status_code, 200, "login gagal (sesi tak valid)", Status.MUMBLE)
        self.assert_eq(me.json().get("username"), st["u"], "sesi user salah stlh login", Status.MUMBLE)

        r = s.get(f"/napi/collections/{st['cid']}")
        self.assert_eq(r.status_code, 200, "koleksi tak terambil", Status.CORRUPT)
        # Dicek via field JSON "description" yg sudah di-parse (disalin
        # verbatim dari body create() saat put(), lihat catatan #4 di atas),
        # bukan r.text mentah, supaya tak kebetulan cocok field lain (mis.
        # "name"/"public_id"/"username").
        self.assert_in(flag, r.json().get("description") or "", "flag tak ada di deskripsi koleksi", Status.CORRUPT)
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
