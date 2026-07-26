#!/usr/bin/env python3
import random
import re
import sys
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4) — _lib SEKALI di
# /checkers/_lib, checker ini di /checkers/eno10_superregister/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

PORT = 6767

# --- Protokol dikonfirmasi thd instance HIDUP (bukan tebakan dari `strings`,
# lihat laporan task-9-report.md utk transkrip lengkap). Ringkasnya, brief
# SALAH di banyak tempat:
#   1. Register butuh TIGA field (Username, Password, Home Address), bukan
#      dua spt `Register <user> <pass>` di brief.
#   2. Login: prompt "Username: " lalu "Password: " terpisah — bukan satu
#      baris `Login <user> <pass>`.
#   3. Command utk bikin kendaraan adalah "add" (bukan "AddVehicle"),
#      interaktif: kirim "add" -> prompt "Enter details (...)"-> satu baris
#      CSV "Make,Model,Year,Color,VIN,Note". TIDAK ada re-auth password
#      (string "Re-enter password to add a vehicle:" ada di binary tapi
#      TAK PERNAH muncul di transkrip nyata utk user clearance biasa —
#      kemungkinan dipakai jalur lain/clearance lain. Diverifikasi live:
#      re-auth TIDAK terjadi utk alur put() checker ini).
#   4. PALING PENTING: respons "add" TIDAK PERNAH mencetak ID kendaraan
#      ("Added new vehicle: <id>" ternyata adalah teks LOG internal utk
#      "history", dan isinya MAKE bukan angka — bukan echo ke klien saat
#      add). Jadi id kendaraan harus digali lewat "search <make>" pakai
#      Make unik yg kita sendiri set saat add (respons: "[<id>] <make>
#      <model>").
#   5. Skema DB (dibaca dari `strings` binary) TAK PUNYA tabel notes
#      terpisah — "maintenance_note" adalah kolom pada vehicles. Jadi
#      "ReadNote [Vehicle ID] [Note ID]" itu SEBENARNYA "ReadNote
#      [VehicleID milikmu, utk auth] [ID kendaraan target, dibaca
#      note-nya]" — dua-duanya sama2 vehicle id (arg kedua boleh milik
#      SIAPA SAJA, itulah IDOR vuln service ini: `SELECT id FROM vehicles
#      WHERE id=? AND user_id=?` mengotorisasi via arg PERTAMA, lalu
#      `SELECT maintenance_note FROM vehicles WHERE id=?` membaca arg
#      KEDUA tanpa filter user_id). Checker ini tak perlu (dan tak boleh)
#      bergantung pada vuln itu utk round-trip miliknya sendiri — vid dan
#      nid yg disimpan di state SAMA PERSIS (vehicle kita sendiri, dibaca
#      dgn otorisasi milik sendiri), jadi state cukup simpan satu id "v".
#
# Prompt persis (byte-for-byte, dari transkrip live):
#   banner ...............: "\n=== SUPERREGISTER Vehicle Management System ===
#                             \nCommands: Login, Register, Exit\n> "
#   register -> username ..: "Choose a Username: "
#   username -> password ...: "Choose a Password: "
#   password -> address ....: "Enter your Home Address: "
#   address -> (balik ke banner, diakhiri "> ")
#   login -> username ......: "Username: "
#   username -> password ...: "Password: "
#   password -> hasil ......: diakhiri "> " baik sukses (MAIN TERMINAL) maupun
#                             gagal ("Invalid credentials." + banner lagi)
#   add -> detail ...........: "Enter details (Make,Model,Year,Color[,VIN,Note]):
#                               \n> "
#   detail -> hasil .........: diakhiri "> " (balik ke MAIN TERMINAL)
#   search/readnote -> hasil : diakhiri "> "
# Semua respons "selesai" berakhir dgn byte literal "> " (prompt), dan tak
# ada satupun teks isi (menu/pesan) yg kebetulan mengandung "> " di tengah —
# jadi recv_until(b"> ") aman dipakai sbg delimiter akhir-respons, KECUALI
# utk 3 prompt field tunggal (Username/Password/Address) yg tak diakhiri
# "> " sama sekali dan harus dikenali via teks prompt-nya sendiri persis
# (memakai delimiter generik spt b": " akan berhenti kepagian di tengah
# teks spt "Clearance Level: " dan bikin desync — lihat catatan brief soal
# recv(N) tetap; masalah yg sama berlaku utk delimiter yg terlalu generik).
PROMPT = b"> "
P_USERNAME_CHOOSE = b"Choose a Username: "
P_PASSWORD_CHOOSE = b"Choose a Password: "
P_ADDRESS = b"Enter your Home Address: "
P_USERNAME = b"Username: "
P_PASSWORD = b"Password: "
BANNER_MARK = b"SUPERREGISTER"


class Checker(BaseChecker):
    def check(self):
        c = A.LineClient(self.host, PORT)
        try:
            banner = c.recv_until(PROMPT)
            self.assert_in(BANNER_MARK, banner, "banner salah", Status.MUMBLE)
            # Bukan cuma baca banner statis (bisa saja stub) — buktikan loop
            # dispatch command beneran hidup dgn satu interaksi riil.
            c.sendline("exit")
            resp = c.recv_until(b"\n")
            self.assert_in(b"Goodbye", resp, "exit tak direspons benar", Status.MUMBLE)
        finally:
            c.close()
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        u, p = A.rand_username(), A.rand_password()
        addr = A.rand_text(20)
        # "make" dipakai jg sbg kunci pencarian utk menggali vehicle id
        # balik (lihat catatan di atas) — rand_username() cukup unik &
        # bebas spasi/koma, jadi aman dipakai sbg field CSV maupun query
        # `search`.
        make = A.rand_username()
        model = A.rand_text(8)
        year = str(random.randint(1990, 2024))
        color = A.rand_text(6)
        vin = A.rand_password()[:12]

        c = A.LineClient(self.host, PORT)
        try:
            c.recv_until(PROMPT)

            c.sendline("register")
            c.recv_until(P_USERNAME_CHOOSE)
            c.sendline(u)
            c.recv_until(P_PASSWORD_CHOOSE)
            c.sendline(p)
            c.recv_until(P_ADDRESS)
            c.sendline(addr)
            reg_resp = c.recv_until(PROMPT)
            self.assert_in(b"Registration successful", reg_resp, "registrasi gagal", Status.MUMBLE)

            c.sendline("login")
            c.recv_until(P_USERNAME)
            c.sendline(u)
            c.recv_until(P_PASSWORD)
            c.sendline(p)
            login_resp = c.recv_until(PROMPT)
            self.assert_in(b"Login successful", login_resp, "login gagal", Status.MUMBLE)

            c.sendline("add")
            c.recv_until(PROMPT)  # "Enter details (...):\n> "
            c.sendline(f"{make},{model},{year},{color},{vin},{flag}")
            add_resp = c.recv_until(PROMPT)
            self.assert_in(b"Vehicle added successfully", add_resp, "tambah kendaraan gagal", Status.MUMBLE)

            # "add" tak pernah mengembalikan id (lihat catatan panjang di
            # atas) — gali balik via "search <make>" krn make kita unik.
            c.sendline(f"search {make}")
            search_resp = c.recv_until(PROMPT)
            vid = self._parse_id(search_resp, make)
            self.assert_(vid is not None, "id kendaraan tak diperoleh dari search", Status.MUMBLE)
        finally:
            c.close()

        self.cquit(Status.OK, A.encode_state(u=u, p=p, v=vid))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        c = A.LineClient(self.host, PORT)
        try:
            c.recv_until(PROMPT)

            c.sendline("login")
            c.recv_until(P_USERNAME)
            c.sendline(st["u"])
            c.recv_until(P_PASSWORD)
            c.sendline(st["p"])
            login_resp = c.recv_until(PROMPT)
            # Login gagal (kredensial salah/hilang) HARUS MUMBLE, bukan
            # CORRUPT — auth rusak beda kasus dgn flag hilang/diubah.
            # Dicek SEBELUM apa pun disimpulkan soal isi note.
            self.assert_in(b"Login successful", login_resp, "login gagal", Status.MUMBLE)

            # vid dipakai dobel: arg pertama (otorisasi kendaraan MILIK
            # SENDIRI) dan arg kedua (target note dibaca) — keduanya
            # kendaraan yg sama, jalur "sah" tanpa bergantung pd IDOR
            # service ini (lihat catatan panjang di atas soal skema DB).
            c.sendline(f"readnote {st['v']} {st['v']}")
            note_resp = c.recv_until(PROMPT)
            # Genuine round-trip: assert atas byte yg BALIK dari server utk
            # vehicle/note spesifik ini (bukan sesuatu yg sesi ini sendiri
            # kirim, dan "Authorization failed"/vehicle tak ada = tak
            # mengandung flag = gagal di sini, bukan lolos kebetulan).
            self.assert_in(flag.encode(), note_resp, "flag tak ada di note", Status.CORRUPT)
        finally:
            c.close()

        self.cquit(Status.OK)

    def _parse_id(self, resp, make):
        # Format baris hasil "search": "[<id>] <make> <model>". Diikat ke
        # `make` persis milik kita spy tak salah ambil baris lain (bukan
        # regex spekulatif spt di brief — ini dicocokkan ke format nyata
        # yg sudah dikonfirmasi dari transkrip live).
        m = re.search(rb"\[(\d+)\]\s+" + re.escape(make.encode()), resp)
        return m.group(1).decode() if m else None


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
