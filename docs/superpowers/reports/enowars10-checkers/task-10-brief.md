### Task 10: Checker inbox (:4321 SMTP / :1234 IMAP)

**Files:** Create `checkers/enowars10/inbox/checker.py`; Modify config.
**Interfaces:** Consumes `adlab_eno`. Kontrak (recon §8): SMTP `AUTH PLAIN` di :4321; IMAP LOGIN di :1234. Implementasi custom — coba stdlib `smtplib`/`imaplib` dulu; bila handshake tak standar, turun ke `A.LineClient` protokol manual.

- [ ] **Step 1: Tulis checker** (mulai dari stdlib; siapkan fallback `A.LineClient` bila server custom menolak greeting `smtplib`/`imaplib`)

```python
#!/usr/bin/env python3
import sys, smtplib, imaplib, email
from email.message import EmailMessage
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A

SMTP_PORT, IMAP_PORT = 4321, 1234

class Checker(BaseChecker):
    def check(self):
        try:
            c = A.LineClient(self.host, IMAP_PORT); g = c.recv(128); c.close()
            self.assert_in(b"OK", g, "greeting IMAP salah", Status.MUMBLE)
        except Exception as e:
            self.cquit(A.status_for(e), "imap down")
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        # Registrasi user dikonfirmasi terhadap internal/session/commands.go saat
        # Step 2 (auto-create saat LOGIN vs endpoint daftar). Titik-awal: SMTP
        # AUTH PLAIN lalu kirim ke mailbox user yg sama.
        u, p = A.rand_username().lower(), A.rand_password()
        sm = smtplib.SMTP(self.host, SMTP_PORT, timeout=10)
        try:
            sm.ehlo()
            sm.login(u, p)                       # AUTH PLAIN
            msg = EmailMessage(); msg["From"] = f"{u}@inbox"; msg["To"] = f"{u}@inbox"
            msg["Subject"] = A.rand_text(6); msg.set_content(flag)
            sm.send_message(msg)
        finally:
            sm.quit()
        self.cquit(Status.OK, A.encode_state(u=u, p=p))

    def get(self, flag_id, flag, vuln):
        st = A.decode_state(flag_id)
        im = imaplib.IMAP4(self.host, IMAP_PORT)
        try:
            im.login(st['u'], st['p']); im.select("INBOX")
            _, ids = im.search(None, "ALL")
            found = False
            for num in ids[0].split():
                _, data = im.fetch(num, "(RFC822)")
                if flag.encode() in (data[0][1] or b""):
                    found = True; break
            self.assert_(found, "flag tak ada di mailbox", Status.CORRUPT)
        finally:
            im.logout()
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
```
- [ ] **Step 2: Deploy (Go IMAP/SMTP) + gate 3-langkah** — tentukan cara registrasi user (recon: LOGIN di IMAP commands; mungkin auto-create). Iterasi sampai `101/101/101`.
- [ ] **Step 3: Gate jalur gagal** (102/104).
- [ ] **Step 4: Daftar config** (`name: inbox`, `checker_timeout: 25`), verifikasi `UP`.
- [ ] **Step 5: Commit** `feat(eno10): checker inbox (SMTP+IMAP) + gate lolos`.

---

