#!/usr/bin/env python3
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4/5/6/7 di greple/d3pl0y/
# flagdrive/signmemaybe/overeats/funsplash checker.py) — _lib SEKALI di
# /checkers/_lib, checker ini di /checkers/eno10_leet_date/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 6789

# Koreksi menyeluruh thd brief (dikonfirmasi baca src/internal/handlers/
# {router,auth,profiles,health}.go + src/internal/auth/sessions.go +
# src/internal/config/config.go + docker-compose.yml + web/nginx.conf +
# web/src/api.ts, LALU diverifikasi ulang via python3-requests langsung ke
# instance live dari dalam container celery — bukan tebakan):
#
# 1. Topologi 6-container: service `web` (nginx) publish HOST "6789:8080"
#    (docker-compose.yml) sedangkan container app Go (`leetdate`) sendiri
#    cuma listen :8000 di jaringan compose privat (IP tetap 172.28.0.10,
#    TANPA published port ke host sama sekali) — nginx location /api/
#    reverse-proxy ke leetdate_up (172.28.0.10:8000) (web/nginx.conf:16-28).
#    Ini PERSIS pola "host publish ke port internal beda" yg diperingatkan
#    utk Task 6 (overeats): attach-ke-forcad_default + gate-IP-container
#    TIDAK BISA dipakai di sini (tak ada container yg listen :6789 sama
#    sekali secara internal). Servis ini karenanya dijalankan di VM tim
#    (10.13.37.12), digate ke IP VM itu, BUKAN IP container/server host.
#
# 2. POST /api/register WAJIB field "display_name" (auth.go:27 registerReq;
#    divalidasi panjang 1-64 auth.go:55-58) — draf brief cuma kirim
#    handle+password, dikonfirmasi live balas 400 "display_name must be
#    1-64 chars" tanpa field ini. handle sendiri di-lowercase SEBELUM
#    divalidasi regex ^[a-z0-9_]{3,20}$ (auth.go:48,51), jadi rand_username()
#    adlab_eno (mengandung huruf kapital) aman dipakai apa adanya.
#
# 3. Register SUDAH auto-login: auth.go:85-90 memanggil auth.CreateSession
#    + auth.SetSessionCookie tepat sama seperti Login (auth.go:126-131),
#    respons 201 Created (bukan 200 — tapi `//100==2` di draf brief kebetulan
#    tetap benar krn 201//100==2 juga). Dikonfirmasi live: GET /api/me
#    langsung 200 tepat setelah register, TANPA panggilan /api/login
#    terpisah. Panggilan POST /api/login stlh register (spt draf brief) jadi
#    REDUNDAN, dihapus dari put(): PATCH /api/me ada di belakang middleware
#    auth.RequireAuth (router.go:53-54) yg 401 kalau cookie tak valid, jadi
#    assert 200 di bawah SEKALIGUS jadi bukti sesi register valid (bukan
#    diasumsikan dari status sukses register semata).
#
# 4. Field bio dikonfirmasi: PATCH /api/me, body JSON {"bio": ...}
#    (profiles.go:57-65 patchReq.Bio; profiles.go:214-222 — disimpan APA
#    ADANYA via nullIfEmpty, TANPA strings.TrimSpace tak spt field city/
#    gender). Respons PATCH sukses (200) BUKAN echo body request — PatchMe
#    memanggil d.Me(c) di baris akhir (profiles.go:274) yg re-SELECT penuh
#    dari Postgres (profiles.go:74-87), jadi field "bio" pd respons PATCH
#    sendiri sudah genuine round-trip lewat DB, dikonfirmasi live.
#
# 5. GET /api/users/{handle} (profiles.go:103-138 PublicProfile) terdaftar
#    di grup `api` LUAR (router.go:50), BUKAN di grup `authed` (router.go:
#    53-75 — perhatikan auth.RequireAuth cuma di-`Use` pd subgroup ini) —
#    rute ini PUBLIK, tanpa cookie/login sama sekali. Dikonfirmasi live pakai
#    session Python BARU (tanpa cookie apa pun) tetap balas 200 + bio
#    lengkap; juga konsisten dgn web/src/api.ts:150-151 (`getUser` dipanggil
#    independen dari sesi). get() karenanya TIDAK login, state cukup simpan
#    handle. Handle tak ditemukan ATAU format tak valid (profiles.go:105-108)
#    SAMA-SAMA balas 404 "user not found" (dikonfirmasi live) — cocok dgn
#    kontrak gate "GET flag_id palsu (JSON valid, handle tak ada) -> CORRUPT".
#
# 6. Cookie sesi `ld_session` (sessions.go:17) diset SameSite=Lax + HttpOnly
#    + Secure=cfg.CookieSecure (sessions.go:79-82). cfg.CookieSecure di
#    deployment ini FALSE krn docker-compose.yml set literal
#    COOKIE_SECURE="0" (config.go:26 `== "1"`) — dikonfirmasi live lewat
#    header Set-Cookie (tak ada flag `Secure`) DAN lewat requests.Session
#    yg berhasil kirim balik cookie tsb ke PATCH /api/me tanpa perlakuan
#    khusus. BEDA dgn jebakan Task 7 (Secure bergantung hostname request):
#    di sini False tak bergantung host sama sekali, jadi TIDAK perlu
#    _sync_cookie_header manual.
#
# 7. check() pakai GET /api/healthz (health.go:9-11, balas {"ok":true})
#    yg diproksi nginx location /api/ (nginx.conf:16) ke backend Go —
#    pemeriksaan liveness APLIKASI asli (postgres+gin), bukan cuma
#    index.html statis nginx spt "/" yg dipakai draf brief/preseden
#    funsplash utk servis yg memang TANPA rute health tersendiri.


class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        r = s.get("/api/healthz", allow_redirects=False)
        self.assert_eq(r.status_code, 200, "API /api/healthz tidak sehat", Status.MUMBLE)
        data = self.get_json(r, "API /api/healthz balas bukan JSON", Status.MUMBLE)
        self.assert_(data.get("ok") is True, "API /api/healthz balas ok != true", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        u, p, dn = A.rand_username(), A.rand_password(), A.rand_username()

        r = s.post(
            "/api/register",
            json={"handle": u, "display_name": dn, "password": p},
            allow_redirects=False,
        )
        self.assert_eq(r.status_code, 201, "register gagal", Status.MUMBLE)
        reg = self.get_json(r, "register balas bukan JSON", Status.MUMBLE)
        handle = reg.get("handle")
        self.assert_(bool(handle), "handle kosong stlh register", Status.MUMBLE)

        # Tak ada POST /api/login terpisah di sini — lihat catatan #3 di
        # atas: register sudah auto-login, cookie sesi sudah ada di `s`.
        r = s.patch("/api/me", json={"bio": flag}, allow_redirects=False)
        self.assert_eq(r.status_code, 200, "set bio (PATCH /api/me) gagal", Status.MUMBLE)
        me = self.get_json(r, "PATCH /api/me balas bukan JSON", Status.MUMBLE)
        self.assert_eq(me.get("bio"), flag, "bio tak tersimpan persis stlh PATCH", Status.MUMBLE)

        self.cquit(Status.OK, A.encode_state(h=handle))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        s = A.http(self.host, PORT)

        # Anonim, TANPA login — lihat catatan #5 di atas: rute publik.
        r = s.get(f"/api/users/{st['h']}", allow_redirects=False)
        self.assert_eq(r.status_code, 200, "profil tak terambil (GET /api/users/{handle})", Status.CORRUPT)
        data = self.get_json(r, "profil balas bukan JSON", Status.MUMBLE)
        self.assert_eq(data.get("bio"), flag, "flag tak ada/berubah di bio profil", Status.CORRUPT)
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
