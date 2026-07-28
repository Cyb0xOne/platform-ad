"""Dashboard A/D custom — backend ke Postgres ForcAD.

Prinsip: dashboard TIDAK PERNAH menulis ke DB engine. Semua endpoint DB adalah
SELECT. Aksi kontrol (start/stop ronde dsb.) baru ditambahkan di Fase 4 lewat
mekanisme resmi ForcAD (control.py), bukan lewat UPDATE langsung — menulis mentah
ke tabel engine berisiko mengorupsi state permainan.

Pengecualian sadar: POST /api/team/{id}/authorized_key menulis ke VULNBOX (bukan
ke DB engine) untuk menitipkan pubkey peserta. Platform ini dipakai untuk latihan
dan debug pembangunan A/D, dan dashboard TIDAK punya autentikasi — artinya siapa
pun yang menjangkau :8090 bisa memberi dirinya akses root ke vulnbox mana pun.
Trade-off ini diterima secara sadar untuk konteks lab; jangan bawa endpoint ini
ke lingkungan kompetisi tanpa memasang auth lebih dulu.

Sumber data (tabel ForcAD):
  teams, tasks            — daftar tim & service
  teamtasks               — state sekarang per (tim, task): status/skor/SLA
  teamtaskslog            — snapshot per ronde -> timeline
  stolenflags + flags     — log serangan (siapa mencuri dari siapa)
  gameconfig              — ronde berjalan
"""

import os
import re
import subprocess
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DSN = os.environ['FORCAD_DSN']  # postgresql://user:pass@host:5432/forcad
FRONTEND = os.path.join(os.path.dirname(__file__), 'static')
VM_SSH_KEY = os.environ.get('VM_SSH_KEY', '/secrets/vmkey')
VM_SSH_USER = os.environ.get('VM_SSH_USER', 'reky')

app = FastAPI(title='AD Dashboard', docs_url='/api/docs')

# Status ForcAD (backend/lib/models/types.py) -> label ringkas untuk UI.
STATUS = {101: 'UP', 102: 'CORRUPT', 103: 'MUMBLE', 104: 'DOWN', 110: 'ERROR', -1: 'N/A'}

# Tabel `tasks` ForcAD tidak punya kolom port, jadi peta ini dirawat manual —
# sumber kebenaran `docker ps` di VM tim, perbarui saat roster berubah.
# String (bukan int) karena ada rentang & ganda; protokol sengaja tidak disimpan.
SERVICE_PORTS = {
    'example': '10000',
    'greple': '7770-7778',
    'd3pl0y': '2553',
    'flagdrive': '4859',
    'signmemaybe': '1984',
    'funsplash': '1337',
    'superregister': '6767',
    'inbox': '1234, 4321',
    'overeats': '5432',
    'leet-date': '6789',
}


@contextmanager
def cursor():
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def _sla_frac(row):
    """checks_passed / checks, dengan 1.0 saat belum ada check."""
    return row['checks_passed'] / row['checks'] if row['checks'] else 1.0


def _sla(row):
    return round(100.0 * _sla_frac(row), 1)


@app.get('/api/game')
def game():
    with cursor() as cur:
        cur.execute('SELECT real_round, flag_lifetime, round_time, game_running FROM gameconfig LIMIT 1')
        return cur.fetchone() or {}


@app.get('/api/scoreboard')
def scoreboard():
    """Ranking tim + rincian per service (grid utama)."""
    with cursor() as cur:
        cur.execute(
            '''SELECT id, name, checker_type, checker_timeout,
                      puts, gets, places, get_period, default_score
               FROM tasks ORDER BY id'''
        )
        tasks = [dict(t, ports=SERVICE_PORTS.get(t['name'], '?')) for t in cur.fetchall()]
        cur.execute(
            '''SELECT tt.team_id, tm.name AS team, tm.highlighted, tm.ip, tm.token,
                      tt.task_id, tt.status, tt.score, tt.stolen, tt.lost,
                      tt.checks, tt.checks_passed
               FROM teamtasks tt JOIN teams tm ON tm.id = tt.team_id'''
        )
        rows = cur.fetchall()

    teams = {}
    for r in rows:
        t = teams.setdefault(r['team_id'], {
            'team_id': r['team_id'], 'team': r['team'],
            'highlighted': r['highlighted'], 'ip': r['ip'], 'token': r['token'],
            'total': 0.0, 'services': {},
        })
        # Total = Σ(score × SLA), formula ctftime resmi ForcAD
        # (backend/lib/storage/game.py:construct_ctftime_scoreboard). Skor mentah
        # dibobot uptime, jadi dashboard menampilkan angka yang SAMA dengan
        # scoreboard engine — bukan hitungan sendiri yang berbeda.
        t['total'] += r['score'] * _sla_frac(r)
        t['services'][r['task_id']] = {
            'status': STATUS.get(r['status'], str(r['status'])),
            'score': round(r['score'], 1),           # skor mentah per service
            'stolen': r['stolen'], 'lost': r['lost'], 'sla': _sla(r),
        }
    ranked = sorted(teams.values(), key=lambda x: x['total'], reverse=True)
    for i, t in enumerate(ranked, 1):
        t['pos'] = i
        t['total'] = round(t['total'], 1)
    return {'tasks': tasks, 'teams': ranked}


@app.get('/api/attacks')
def attacks(limit: int = 50):
    """Log serangan: siapa mencuri flag siapa, di service apa, kapan."""
    with cursor() as cur:
        cur.execute(
            '''SELECT sf.submit_time, att.name AS attacker,
                      vic.name AS victim, t.name AS service, f.round AS flag_round
               FROM stolenflags sf
               JOIN flags f  ON f.id = sf.flag_id
               JOIN teams att ON att.id = sf.attacker_id
               JOIN teams vic ON vic.id = f.team_id
               JOIN tasks t   ON t.id  = f.task_id
               ORDER BY sf.submit_time DESC LIMIT %s''', (limit,))
        return [dict(r, submit_time=r['submit_time'].isoformat()) for r in cur.fetchall()]


@app.get('/api/firstblood')
def firstblood():
    """Pencuri pertama tiap service (first blood), dikunci per task_id.

    DISTINCT ON (postgres) mengambil baris paling awal per task setelah diurutkan
    submit_time menaik — satu query, tanpa subquery/window. Dikembalikan sebagai
    map task_id -> {attacker, submit_time} supaya frontend cukup lookup, bukan scan.
    """
    with cursor() as cur:
        cur.execute(
            '''SELECT DISTINCT ON (f.task_id)
                      f.task_id, att.name AS attacker, sf.submit_time
               FROM stolenflags sf
               JOIN flags f   ON f.id  = sf.flag_id
               JOIN teams att ON att.id = sf.attacker_id
               ORDER BY f.task_id, sf.submit_time ASC'''
        )
        return {
            r['task_id']: {'attacker': r['attacker'],
                           'submit_time': r['submit_time'].isoformat()}
            for r in cur.fetchall()
        }


@app.get('/api/timeline')
def timeline():
    """Skor efektif per tim per ronde (untuk grafik).

    Memakai formula ctftime yang sama dengan /api/scoreboard: Σ(score × SLA).
    NULLIF menjaga pembagian aman saat checks = 0 (COALESCE -> faktor 1)."""
    with cursor() as cur:
        cur.execute(
            '''SELECT l.round, l.team_id, tm.name AS team,
                      SUM(l.score * COALESCE(l.checks_passed::float / NULLIF(l.checks,0), 1)) AS score
               FROM teamtaskslog l JOIN teams tm ON tm.id = l.team_id
               GROUP BY l.round, l.team_id, tm.name ORDER BY l.round'''
        )
        return [dict(r, score=round(r['score'], 1)) for r in cur.fetchall()]


# Hanya tipe kunci yang dipakai OpenSSH modern; baris baru tidak akan pernah lolos
# sehingga input tidak bisa menyelundupkan kunci kedua atau opsi authorized_keys
# (mis. command=/from=) yang mengubah arti berkas.
PUBKEY_RE = re.compile(
    r'(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) '
    r'[A-Za-z0-9+/]{32,1024}={0,3}'
    r'(?: [\w@.\-]{1,64})?'
)


class AuthorizedKey(BaseModel):
    key: str


@app.post('/api/team/{team_id}/authorized_key')
def add_authorized_key(team_id: int, body: AuthorizedKey):
    """Titipkan pubkey peserta ke vulnbox tim agar bisa SSH sendiri."""
    key = body.key.strip()
    if not PUBKEY_RE.fullmatch(key):
        raise HTTPException(
            status_code=400,
            detail='Format public key tidak dikenali. Tempel isi berkas .pub '
                   '(mis. ssh-ed25519 AAAA... nama), satu baris.',
        )

    with cursor() as cur:
        cur.execute('SELECT name, ip FROM teams WHERE id = %s', (team_id,))
        team = cur.fetchone()
    if not team:
        raise HTTPException(status_code=404, detail='Tim tidak ditemukan.')

    # Kunci dikirim lewat STDIN, tidak pernah disisipkan ke string perintah, jadi
    # tidak ada jalur command injection walau regex di atas suatu saat dilonggarkan.
    # sort -u membuat pemasangan ulang kunci yang sama tidak menumpuk.
    remote = (
        'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
        'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && '
        'sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && '
        'chmod 600 ~/.ssh/authorized_keys && wc -l < ~/.ssh/authorized_keys'
    )
    try:
        proc = subprocess.run(
            ['ssh', '-i', VM_SSH_KEY, '-o', 'BatchMode=yes',
             '-o', 'StrictHostKeyChecking=no', '-o', 'IdentitiesOnly=yes',
             '-o', 'ConnectTimeout=8', f'{VM_SSH_USER}@{team["ip"]}', remote],
            input=key + '\n', capture_output=True, text=True, timeout=25,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='Vulnbox tidak merespons.')
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f'Gagal memasang kunci di {team["ip"]}: {proc.stderr.strip()[:200]}',
        )
    return {
        'ok': True, 'team': team['name'], 'ip': team['ip'],
        'user': VM_SSH_USER, 'total_keys': proc.stdout.strip(),
    }


@app.get('/api/health')
def health():
    try:
        with cursor() as cur:
            cur.execute('SELECT 1')
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


@app.get('/')
def index():
    return FileResponse(os.path.join(FRONTEND, 'index.html'))


app.mount('/', StaticFiles(directory=FRONTEND), name='static')
