### Task 2: Checker greple (:7777) — template HTTP

Service Zig; flag di pastebin. Ini template semua checker HTTP; task berikut mengikuti bentuk sama dengan kontrak endpoint berbeda.

**Files:**
- Create: `checkers/enowars10/greple/checker.py`
- Create: `deploy/enowars10-deploy.sh`
- Modify: `forcad/config.enowars10.yml` (buat, entri greple)

**Interfaces:**
- Consumes: `adlab_eno` (Task 1) — `http`, `rand_username`, `rand_password`, `rand_text`, `encode_state`, `decode_state`, `status_for`.
- Produces: pola `Checker(BaseChecker)` dengan `check/put/get`, entrypoint standar; dikonsumsi Task 3–12 sebagai bentuk acuan.

Kontrak endpoint (dari recon §7): `POST /pastebin` (form/JSON body memuat teks paste) → respons memuat id hex; `GET /p/{hex}` → teks paste. `POST /user_account` login bila perlu; pastebin bisa anonim.

- [ ] **Step 1: Tulis checker**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from checklib import BaseChecker, Status, cquit
import adlab_eno as A
import re

PORT = 7777

class Checker(BaseChecker):
    def check(self):
        s = A.http(self.host, PORT)
        r = s.get("/")
        self.assert_eq(r.status_code, 200, "index down", Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        s = A.http(self.host, PORT)
        r = s.post("/pastebin", data={"content": flag})
        self.assert_eq(r.status_code // 100, 2, "pastebin tolak simpan", Status.MUMBLE)
        m = re.search(r"/p/([0-9a-f]+)", r.text) or re.search(r"([0-9a-f]{8,})", r.text)
        self.assert_(m is not None, "id paste tak ditemukan", Status.MUMBLE)
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
```

- [ ] **Step 2: Tulis helper deploy service (dipakai semua task berikut)**

```bash
# deploy/enowars10-deploy.sh — jalankan DI SERVER
# pemakaian: enowars10-deploy.sh <service-dir> [up|down]
#   contoh: enowars10-deploy.sh greple up   -> build+jalankan di host, di network forcad_default
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin
SVC="$1"; ACT="${2:-up}"
SRC="$HOME/workspaces/cylab/ctf/attack-defense/enowars10-2026/shining-arc-team-repo/$SVC"
# CATATAN: bank soal ada di laptop, bukan server. Untuk uji, rsync source service
# ke server lebih dulu: rsync -az <laptop>/$SVC reky@server:~/adlab/eno10/$SVC
WORK="$HOME/adlab/eno10/$SVC"
cd "$WORK"
if [ "$ACT" = "down" ]; then docker compose down -v; exit 0; fi
# sambungkan ke network yang sama dgn celery agar checker menjangkau via nama/IP
docker compose up -d --build
docker compose ps
```

Catat batasan di komentar: service enowars10 memakai network `default` sendiri; agar celery menjangkaunya, jalankan service dengan IP host yang terekspos (port publish) lalu gate memakai `host.docker.internal`/IP host, ATAU jalankan service di VM tim (10.13.37.x) seperti service Fase 1. Untuk uji cepat, publish port ke host dan gate pakai IP host server.

- [ ] **Step 3: Deploy service greple + jalankan gate**

Run (di server, service greple sudah berjalan di `<svc-ip>:7777`):
```bash
C=$(docker ps -qf name=forcad-celery | head -1)
# salin harness + checker ke container
docker exec $C mkdir -p /checkers/eno10_greple
docker cp checkers/enowars10/_lib $C:/checkers/eno10_greple/_lib
docker cp checkers/enowars10/greple/checker.py $C:/checkers/eno10_greple/checker.py
docker exec $C chmod +x /checkers/eno10_greple/checker.py
FLAG="ENOTESTFLAG$(date +%s)AAAAAAAAAAAA="
docker exec $C /checkers/eno10_greple/checker.py check <svc-ip>; echo "check=$?"
docker exec $C /checkers/eno10_greple/checker.py put <svc-ip> "" "$FLAG" 0 > /tmp/g.out; echo "put=$?"; FID=$(cat /tmp/g.out)
docker exec $C /checkers/eno10_greple/checker.py get <svc-ip> "$FID" "$FLAG" 0; echo "get=$?"
```
Expected: `check=101 put=101 get=101`, dan baris stdout put berbentuk `{"pid":"..."}`.

- [ ] **Step 4: Gate jalur gagal**

Run:
```bash
docker exec $C /checkers/eno10_greple/checker.py get <svc-ip> '{"pid":"deadbeef"}' "$FLAG" 0; echo "corrupt=$?"
docker exec $C /checkers/eno10_greple/checker.py check 10.13.37.99; echo "down=$?"
```
Expected: `corrupt=102`, `down=104`. Bila request shape meleset (mis. field body `content` salah nama), iterasi checker Step 1 terhadap respons nyata service sampai gate lolos.

- [ ] **Step 5: Daftarkan di config + verifikasi engine**

```yaml
# forcad/config.enowars10.yml — tambahkan ke tasks:
  - name: greple
    checker: eno10_greple/checker.py
    checker_type: ''
    checker_timeout: 20
    puts: 1
    gets: 1
    places: 1
```
Terapkan config (reset+clean+setup+start seperti `deploy/fase05-cutover.sh`), tunggu 1 ronde, konfirmasi log celery `Finished testing … task <greple> … CHECK UP; PUT UP; GET UP`.

- [ ] **Step 6: Commit**

```bash
git add checkers/enowars10/greple/checker.py deploy/enowars10-deploy.sh forcad/config.enowars10.yml
git commit -m "feat(eno10): checker greple (pastebin) + gate lolos"
```

---

