### Task 11: SPIKE Checker mediocre (:1980) — telnet DSM-11

**Best-effort (spec §Risiko).** Bila buntu setelah usaha wajar, dokumentasikan & lanjut; tidak memblokir Task 1–10/12.

**Files:** Create `checkers/enowars10/mediocre/checker.py`; Modify config (hanya bila gate lolos).
**Interfaces:** Consumes `adlab_eno` — `expect_session` (pexpect). Kontrak (recon §10): haproxy :1980 → DSM-11 via terminal; login `MGR` (`DO_NOT_TOUCH_THIS.md`), prompt telnet.

- [ ] **Step 1: Spike interaktif** — sambungkan `telnet <ip> 1980` manual, petakan urutan login DSM-11 + perintah menyimpan/membaca sebuah global/record MUMPS. Catat transcript.
- [ ] **Step 2: Tulis checker** dengan `pexpect` (tambah `pexpect` ke `checkers/requirements.txt`) mengikuti transcript: `put` login→simpan flag di record→state simpan kunci record; `get` login→baca record→assert flag.
- [ ] **Step 3: Gate 3-langkah + jalur gagal**. Bila lolos, daftar config (`name: mediocre`, `checker_timeout: 40`) + verifikasi `UP`. Bila buntu: tulis `checkers/enowars10/mediocre/BLOCKED.md` berisi transcript + hambatan.
- [ ] **Step 4: Commit** `feat(eno10): checker mediocre (DSM-11)` atau `docs(eno10): mediocre spike terblok — transcript`.

---

