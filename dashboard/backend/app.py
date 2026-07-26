"""Dashboard A/D custom — backend read-only ke Postgres ForcAD.

Prinsip: dashboard TIDAK PERNAH menulis ke DB engine. Semua endpoint SELECT.
Aksi kontrol (start/stop ronde dsb.) baru ditambahkan di Fase 4 lewat mekanisme
resmi ForcAD (control.py), bukan lewat UPDATE langsung — menulis mentah ke
tabel engine berisiko mengorupsi state permainan.

Sumber data (tabel ForcAD):
  teams, tasks            — daftar tim & service
  teamtasks               — state sekarang per (tim, task): status/skor/SLA
  teamtaskslog            — snapshot per ronde -> timeline
  stolenflags + flags     — log serangan (siapa mencuri dari siapa)
  gameconfig              — ronde berjalan
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DSN = os.environ['FORCAD_DSN']  # postgresql://user:pass@host:5432/forcad
FRONTEND = os.path.join(os.path.dirname(__file__), 'static')

app = FastAPI(title='AD Dashboard', docs_url='/api/docs')

# Status ForcAD (backend/lib/models/types.py) -> label ringkas untuk UI.
STATUS = {101: 'UP', 102: 'CORRUPT', 103: 'MUMBLE', 104: 'DOWN', 110: 'ERROR', -1: 'N/A'}


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
        cur.execute('SELECT id, name FROM tasks ORDER BY id')
        tasks = cur.fetchall()
        cur.execute(
            '''SELECT tt.team_id, tm.name AS team, tm.highlighted,
                      tt.task_id, tt.status, tt.score, tt.stolen, tt.lost,
                      tt.checks, tt.checks_passed
               FROM teamtasks tt JOIN teams tm ON tm.id = tt.team_id'''
        )
        rows = cur.fetchall()

    teams = {}
    for r in rows:
        t = teams.setdefault(r['team_id'], {
            'team_id': r['team_id'], 'team': r['team'],
            'highlighted': r['highlighted'], 'total': 0.0, 'services': {},
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
