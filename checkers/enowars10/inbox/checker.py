#!/usr/bin/env python3
import sys
import smtplib
import imaplib
from email.message import EmailMessage
from pathlib import Path
# KONTRAK DEPLOY: baris parent.parent mengasumsikan _lib jadi SIBLING dari
# direktori checker ini (lihat catatan Task 2/3/4/9) — _lib SEKALI di
# /checkers/_lib, checker ini di /checkers/eno10_inbox/checker.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

IMAP_PORT = 1234
SMTP_PORT = 4321
TIMEOUT = 10

# --- Protokol dikonfirmasi thd instance HIDUP (docker compose di server,
# di-attach ke forcad_default) DAN thd source Go (internal/session/commands.go,
# internal/imap/parser.go, internal/smtp/server.go, internal/db/db.go). Brief
# ini SALAH pada satu asumsi penting; sisanya benar tapi butuh detail:
#
# 1. AKUN TIDAK auto-create saat LOGIN. `cmdLogin`/`cmdAuthenticate` di
#    commands.go memanggil `s.db.Authenticate(username, password)`, yang
#    gagal (return ok=false) kalau file `users/<u>/password` belum ada — jadi
#    LOGIN ke user yg belum terdaftar dan LOGIN dgn password salah ke user yg
#    SUDAH terdaftar menghasilkan PESAN IDENTIK: "LOGIN failed: invalid
#    credentials" (dikonfirmasi live, byte-for-byte sama). Registrasi HARUS
#    lewat command IMAP kustom "REGISTER <user> <pass>" (cmdRegister, hanya
#    valid di state NotAuthenticated, panggil db.CreateUser lalu
#    db.EnsureInbox). SMTP TIDAK PUNYA cara registrasi sama sekali (AUTH SMTP
#    juga cuma db.Authenticate; RCPT TO butuh db.UserExists). Jadi urutan yg
#    benar: REGISTER dulu via IMAP, baru SMTP AUTH PLAIN dgn kredensial yg
#    sama akan diterima (dan RCPT TO ke mailbox sendiri akan valid).
#
# 2. stdlib `smtplib`/`imaplib` MEMADAI PENUH utk setiap verb STANDAR yg
#    checker ini perlukan — dikonfirmasi live tanpa modifikasi apa pun:
#    EHLO, AUTH PLAIN (smtplib.login), MAIL/RCPT/DATA (smtplib.send_message)
#    di SMTP; LOGIN, SELECT, SEARCH, FETCH, NOOP, CAPABILITY di IMAP.
#    SATU-SATUNYA operasi yg TAK PUNYA representasi stdlib adalah REGISTER
#    itu sendiri — ini bukan server yg "menolak" handshake standar, tapi
#    `imaplib` client library memang tak kenal verb non-standar ini sama
#    sekali (`_simple_command`/`_command` menggerbangi setiap nama command
#    lewat dict internal `Commands` yg cuma berisi verb IMAP4rev1 asli;
#    "REGISTER" bukan anggotanya → `KeyError`). Solusi yg dipakai: `A.LineClient`
#    dipakai SEMPIT hanya utk satu langkah REGISTER (satu request/response),
#    baru koneksi imaplib/smtplib TERPISAH & BERSIH dipakai utk sisanya —
#    BUKAN fallback total ke protokol manual (beda dgn kasus superregister/
#    Task 9 yg memang harus manual penuh krn protokolnya CLI custom, bukan
#    turunan protokol standar sama sekali). Alternatif yg DIHINDARI dgn
#    sengaja: monkey-patch `imaplib.Commands['REGISTER'] = (...)` — jalan,
#    tapi mengubah state GLOBAL modul stdlib demi satu command custom
#    terasa lebih rapuh drpd satu koneksi LineClient sekali pakai.
#
# 3. BUG SERVER YG DITEMUKAN — IMAP APPEND lewat imaplib RUSAK thd server
#    ini (dikonfirmasi via repro live: `imaplib.IMAP4.abort: socket error:
#    EOF` persis pada command SETELAH append() yg "sukses"). Sebab: literal
#    reader server (`consumeLiteral` di internal/imap/parser.go) membaca
#    PERSIS N byte literal via `io.ReadFull`, tapi TAK PERNAH menguras CRLF
#    penutup yang dikirim client SETELAH byte literal (bagian standar framing
#    IMAP: literal diikuti CRLF akhir baris command) — CRLF nyasar itu
#    tertinggal di buffer, lalu dibaca sbg baris KOSONG oleh `ReadCommand()`
#    berikutnya → error "empty tag" → `Session.Run()` diam-diam `return`
#    (Debug flag mati, tak ada log) → koneksi tertutup tanpa respons. Checker
#    ini SENGAJA tidak pernah memakai APPEND — pengiriman flag lewat SMTP DATA
#    saja (yg juga pas dgn tuntutan "buktikan KEDUA port hidup").
#
# 4. JEBAKAN KLASIFIKASI YG DITEMUKAN (diverifikasi live, bukan diasumsikan) —
#    `smtplib.SMTPException` (dan SEMUA turunannya: SMTPAuthenticationError,
#    SMTPRecipientsRefused, SMTPConnectError, SMTPDataError, dst) adalah
#    turunan `OSError` di stdlib (`class SMTPException(OSError)`,
#    dikonfirmasi via `__mro__` DAN via percobaan login/RCPT salah live). Kalau
#    dibiarkan lolos ke handler generik `__main__` (`status_for`), cabang
#    `isinstance(exc, OSError)`-nya akan salah mengklasifikasikan penolakan
#    protokol (mis. password salah, RCPT ke user tak ada) sbg DOWN (104),
#    padahal service-nya HIDUP dan menjawab dgn benar (harusnya MUMBLE, 103).
#    `imaplib.IMAP4.error` (dipakai al. LOGIN gagal) BUKAN turunan OSError,
#    tapi tetap tak dikenali cabang mana pun di `status_for` → jatuh ke
#    default ERROR (110), juga salah. Checker ini menangkap KEDUANYA secara
#    EKSPLISIT & SEMPIT (nama exception spesifik, bukan `except Exception`)
#    di setiap tempat smtplib/imaplib dipakai, lalu menerjemahkan sendiri ke
#    MUMBLE — TIDAK PERNAH membiarkannya jatuh ke handler generik. Ini juga
#    yg dituntut eksplisit oleh task utk get(): "login gagal = MUMBLE, bukan
#    ERROR ataupun CORRUPT".
#
# 5. CACAT SKETSA BRIEF (dihindari, lihat catatan task) — TIDAK PERNAH ada
#    `try: ... assert_*(...) ... except Exception as e: self.cquit(...)`.
#    Setiap `except` di bawah menyebut kelas exception SPESIFIK
#    (`imaplib.IMAP4.error` / `smtplib.SMTPException`), yg BUKAN leluhur
#    `checklib.CheckFinished` (exception yg dipakai `assert_*`/`cquit` utk
#    keluar) — jadi CheckFinished tak pernah tertangkap tak sengaja oleh
#    except tsb, baik assert_* diletakkan di dalam maupun di luar blok try.
#
# 6. TARGET PESAN SPESIFIK di get() — subject unik (`s` di state) dipakai utk
#    `SEARCH SUBJECT "<subj>"` lalu FETCH persis pesan itu; flag diperiksa ADA
#    di badan pesan spesifik itu (bukan scan membabi-buta seluruh mailbox).
#
# Transkrip live (byte-for-byte, sebelum inbox di-attach ke forcad_default,
# port masih host-published):
#   greeting IMAP ......: b'* OK INBOX ready\r\n'
#   greeting SMTP .......: b'220 inbox.local SMTP ready\r\n'
#   REGISTER sukses .....: b'a2 OK REGISTER completed\r\n'
#   REGISTER duplikat ...: b'a3 NO REGISTER failed: user already exists\r\n'
#   LOGIN sukses ........: b'a4 OK LOGIN completed\r\n'
#   LOGIN password salah : b'b1 NO LOGIN failed: invalid credentials\r\n'
#   LOGIN user tak ada ..: b'b2 NO LOGIN failed: invalid credentials\r\n'
#       (PESAN IDENTIK dgn password salah — lihat catatan §1 di atas, ini
#       kenapa kasus bogus/CORRUPT gate TIDAK BOLEH memakai kredensial salah)
#   EHLO ................: 250-inbox.local hello ...\n250-PIPELINING\n
#       250-8BITMIME\n250-AUTH PLAIN\n250-SIZE 1048576\n250 HELP
#
# Data expiry (cron, dibaca dari cleanup.sh + cron.d/inbox-cleanup di source):
#   `*/3 * * * * service /cleanup.sh /maildir` menjalankan
#   `find $MAILDIR/users -mindepth 1 -maxdepth 1 -type d -mmin +12 -exec rm -rf {} +`
#   — SELURUH direktori user (password + mailbox + mail) dihapus ~12-15 menit
#   setelah mtime direktori user itu SENDIRI. Menelusuri db.go: LOGIN/SELECT/
#   FETCH/APPEND biasa TIDAK membuat entri baru langsung di dalam direktori
#   user itu sendiri (EnsureInbox->Subscribe jadi no-op diam2 begitu "INBOX"
#   sudah tersubscribe; file pesan hidup di SUBDIREKTORI mailbox, bukan
#   langsung di direktori user) — jadi jam 12 menit itu praktis mulai dari
#   waktu REGISTER (bukan direfresh oleh get() belakangan). Ini TIDAK diuji
#   dgn menunggu siklus penuh 12-15 menit scr live (mahal dari sisi waktu
#   nyata), tapi mekanismenya dibaca langsung dari shell script yg dieksekusi
#   cron, bukan tebakan `strings` dari biner — keyakinan tinggi walau tak
#   diamati langsung siklusnya.

IMAP_GREETING_MARK = b"INBOX ready"
EHLO_MARK = b"AUTH PLAIN"


class Checker(BaseChecker):
    def check(self):
        # --- IMAP: greeting + CAPABILITY (implisit, lewat constructor
        # imaplib.IMAP4 sendiri) + satu interaksi nyata (NOOP) supaya bukan
        # cuma banner statis yg diperiksa.
        im = None
        try:
            im = imaplib.IMAP4(self.host, IMAP_PORT, timeout=TIMEOUT)
            self.assert_in(IMAP_GREETING_MARK, im.welcome, "banner IMAP salah", Status.MUMBLE)
            self.assert_("REGISTER" in im.capabilities, "capability REGISTER hilang", Status.MUMBLE)
            typ, _ = im.noop()
            self.assert_eq(typ, "OK", "NOOP IMAP gagal", Status.MUMBLE)
        except imaplib.IMAP4.error as e:
            self.cquit(Status.MUMBLE, "IMAP salah", repr(e))
        finally:
            if im is not None:
                try:
                    im.shutdown()
                except Exception:
                    pass

        # --- SMTP: greeting (implisit, lewat constructor) + EHLO nyata,
        # diperiksa bentuk multiline-nya sesuai kontrak server ini.
        sm = None
        try:
            sm = smtplib.SMTP(self.host, SMTP_PORT, timeout=TIMEOUT)
            code, resp = sm.ehlo()
            self.assert_eq(code, 250, "EHLO SMTP gagal", Status.MUMBLE)
            self.assert_in(EHLO_MARK, resp, "EHLO tak sesuai kontrak", Status.MUMBLE)
        except smtplib.SMTPException as e:
            self.cquit(Status.MUMBLE, "SMTP salah", repr(e))
        finally:
            if sm is not None:
                try:
                    sm.close()
                except Exception:
                    pass

        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        u, p = A.rand_username(), A.rand_password()
        subj = "S" + A.rand_username()  # alnum murni, aman sbg token baris
        # tunggal (REGISTER) MAUPUN sbg kriteria SEARCH SUBJECT tanpa spasi.

        # 1. Akun HARUS didaftarkan lebih dulu lewat command IMAP kustom
        # REGISTER (lihat catatan §1 di atas) — bukan verb standar, jadi
        # dipakai A.LineClient utk SATU request/response ini saja.
        c = A.LineClient(self.host, IMAP_PORT, timeout=TIMEOUT)
        try:
            c.recv_until(b"\r\n")  # buang baris greeting "* OK INBOX ready"
            c.sendline(f"a1 REGISTER {u} {p}")
            reg_resp = c.recv_until(b"\r\n")
            self.assert_in(b"OK REGISTER completed", reg_resp, "registrasi IMAP gagal", Status.MUMBLE)
        finally:
            c.close()

        # 2. Kirim flag lewat SMTP: EHLO -> AUTH PLAIN (kredensial yg BARU
        # didaftarkan) -> MAIL/RCPT/DATA ke mailbox milik sendiri, dgn subject
        # unik yg nanti dipakai get() utk menargetkan pesan spesifik ini.
        sm = None
        try:
            sm = smtplib.SMTP(self.host, SMTP_PORT, timeout=TIMEOUT)
            sm.ehlo()
            sm.login(u, p)
            msg = EmailMessage()
            msg["From"] = f"{u}@inbox.local"
            msg["To"] = f"{u}@inbox.local"
            msg["Subject"] = subj
            msg.set_content(flag)
            sm.send_message(msg)
        except smtplib.SMTPException as e:
            self.cquit(Status.MUMBLE, "pengiriman SMTP gagal", repr(e))
        finally:
            if sm is not None:
                try:
                    sm.close()
                except Exception:
                    pass

        self.cquit(Status.OK, A.encode_state(u=u, p=p, s=subj))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        im = None
        try:
            im = imaplib.IMAP4(self.host, IMAP_PORT, timeout=TIMEOUT)
            # Login gagal (kredensial salah/akun kedaluwarsa) HARUS MUMBLE,
            # bukan CORRUPT ataupun ERROR — imaplib.IMAP4.error yg dilempar
            # login() ditangkap oleh except spesifik di bawah, BUKAN
            # dibiarkan lolos ke status_for generik (lihat catatan §4).
            im.login(st["u"], st["p"])

            typ, _ = im.select("INBOX")
            self.assert_eq(typ, "OK", "SELECT INBOX gagal", Status.MUMBLE)

            # Targetkan PERSIS pesan yg kita kirim di put() lewat subject
            # uniknya (bukan scan membabi-buta seluruh mailbox — lihat
            # catatan §6).
            typ, dat = im.search(None, "SUBJECT", f'"{st["s"]}"')
            self.assert_eq(typ, "OK", "SEARCH gagal", Status.MUMBLE)
            ids = dat[0].split() if dat and dat[0] else []
            self.assert_(len(ids) > 0, "pesan dgn subject kita tak ditemukan di mailbox", Status.CORRUPT)

            typ, fdat = im.fetch(ids[-1], "(RFC822)")
            self.assert_eq(typ, "OK", "FETCH pesan gagal", Status.MUMBLE)
            body = fdat[0][1] if fdat[0] else b""
            # Round-trip genuine: flag diperiksa ADA di badan pesan yg BALIK
            # dari server utk pesan spesifik ini (bukan sesuatu yg sesi ini
            # sendiri kirim).
            self.assert_in(flag.encode(), body, "flag tak ada di pesan tersimpan", Status.CORRUPT)
        except imaplib.IMAP4.error as e:
            self.cquit(Status.MUMBLE, "login/IMAP gagal", repr(e))
        finally:
            if im is not None:
                try:
                    im.shutdown()
                except Exception:
                    pass

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
