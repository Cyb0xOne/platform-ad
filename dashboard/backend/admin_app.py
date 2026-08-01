import base64
import hashlib
import json
import os
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ControlAction = Literal["start", "pause", "resume"]

CONTROL_KEY = os.environ.get("CONTROL_KEY", "/secrets/controlkey")
CONTROL_USER = os.environ.get("CONTROL_USER", "reky")
CONTROL_HOST = os.environ.get("CONTROL_HOST", "host.docker.internal")
CONTROL_HISTORY_PATH = os.environ.get(
    "CONTROL_HISTORY_PATH",
    "/data/control-history.jsonl",
)
CONTROL_TIMEOUTS = {"start": 600, "pause": 60, "resume": 60}
VM_SSH_KEY = os.environ.get('VM_SSH_KEY', '/secrets/vmkey')
VM_SSH_USER = os.environ.get('VM_SSH_USER', 'team')
REACT_FRONTEND = os.path.join(os.path.dirname(__file__), "react")

app = FastAPI(
    title="AD Dashboard Admin",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
dashboard = import_module("app")
cursor = dashboard.cursor
OptionalStaticFiles = dashboard.OptionalStaticFiles


def _vm_ssh(ip, remote, stdin=None):
    try:
        return subprocess.run(
            ['ssh', '-i', VM_SSH_KEY, '-o', 'BatchMode=yes',
             '-o', 'StrictHostKeyChecking=no', '-o', 'IdentitiesOnly=yes',
             '-o', 'ConnectTimeout=8', f'{VM_SSH_USER}@{ip}', remote],
            input=stdin, capture_output=True, text=True, timeout=25,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='Vulnbox tidak merespons.')


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


@app.post('/api/admin/team/{team_id}/authorized_key')
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
    proc = _vm_ssh(team['ip'], remote, stdin=key + '\n')
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f'Gagal memasang kunci di {team["ip"]}: {proc.stderr.strip()[:200]}',
        )
    return {
        'ok': True, 'team': team['name'], 'ip': team['ip'],
        'user': VM_SSH_USER, 'total_keys': proc.stdout.strip(),
    }


_KEY_TYPES = frozenset((
    'ssh-ed25519', 'ssh-rsa', 'ssh-dss',
    'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521',
    'sk-ssh-ed25519@openssh.com', 'sk-ecdsa-sha2-nistp256@openssh.com',
))


def _parse_pubkey_line(line):
    parts = line.split()
    for i, token in enumerate(parts):
        if token in _KEY_TYPES and i + 1 < len(parts):
            try:
                # Fingerprint SHA256 gaya OpenSSH: base64 tanpa padding dari
                # sha256(byte kunci mentah) — sama dengan keluaran `ssh-keygen -l`.
                digest = hashlib.sha256(base64.b64decode(parts[i + 1])).digest()
                fp = 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')
            except Exception:
                fp = None
            return {'type': token, 'comment': ' '.join(parts[i + 2:]), 'fingerprint': fp}
    return None


@app.get('/api/admin/team/{team_id}/authorized_keys')
def list_authorized_keys(team_id: int):
    """Daftar public key yang terpasang di vulnbox tim (tipe, fingerprint, komentar)."""
    with cursor() as cur:
        cur.execute('SELECT name, ip FROM teams WHERE id = %s', (team_id,))
        team = cur.fetchone()
    if not team:
        raise HTTPException(status_code=404, detail='Tim tidak ditemukan.')

    remote = ('export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
              'cat ~/.ssh/authorized_keys 2>/dev/null || true')
    proc = _vm_ssh(team['ip'], remote)
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f'Gagal membaca kunci di {team["ip"]}: {proc.stderr.strip()[:200]}',
        )
    keys = [k for k in (_parse_pubkey_line(ln.strip()) for ln in proc.stdout.splitlines())
            if k]
    return {'team': team['name'], 'ip': team['ip'], 'user': VM_SSH_USER, 'keys': keys}


@dataclass(frozen=True)
class ControlResult:
    exit_code: int | None
    stderr: str
    timed_out: bool = False


def run_control(action: ControlAction) -> ControlResult:
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                CONTROL_KEY,
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{CONTROL_USER}@{CONTROL_HOST}",
                action,
            ],
            capture_output=True,
            text=True,
            timeout=CONTROL_TIMEOUTS[action],
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return ControlResult(None, stderr, timed_out=True)
    return ControlResult(proc.returncode, proc.stderr)


def _stderr_tail(stderr: str) -> str:
    return stderr.strip()[-500:]


def _append_control_history(record: dict[str, object]) -> None:
    parent = os.path.dirname(CONTROL_HISTORY_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(CONTROL_HISTORY_PATH, "a", encoding="utf-8") as history:
        history.write(json.dumps(record, separators=(",", ":")) + "\n")


@app.post("/api/admin/control/{action}")
def control(action: ControlAction):
    started = time.monotonic()
    result = run_control(action)
    duration_ms = round((time.monotonic() - started) * 1000)
    stderr_tail = _stderr_tail(result.stderr)

    if result.timed_out:
        outcome = "timeout"
    elif result.exit_code == 0:
        outcome = "ok"
    elif result.exit_code == 75:
        outcome = "busy"
    else:
        outcome = "failed"

    _append_control_history({
        "at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "outcome": outcome,
        "exit_code": result.exit_code,
        "duration_ms": duration_ms,
        "stderr_tail": stderr_tail,
    })

    if result.timed_out:
        raise HTTPException(status_code=504, detail="Control action timed out.")
    if result.exit_code == 75:
        raise HTTPException(status_code=409, detail="Another control action is in flight.")
    if result.exit_code == 64:
        raise HTTPException(
            status_code=500,
            detail="Control wrapper rejected a validated action.",
        )
    if result.exit_code != 0:
        raise HTTPException(
            status_code=502,
            detail=f"Control action failed: {stderr_tail}",
        )
    return {"ok": True, "action": action}


@app.get("/api/admin/control/history")
def control_history():
    try:
        with open(CONTROL_HISTORY_PATH, encoding="utf-8") as history:
            lines = deque(history, maxlen=20)
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in reversed(lines)]


@app.get("/api/admin/teams")
def teams():
    with cursor() as cur:
        cur.execute("SELECT id AS team_id, name AS team, ip FROM teams ORDER BY id")
        return [dict(team) for team in cur.fetchall()]


@app.get("/api/admin/team/{team_id}/token")
def team_token(team_id: int):
    with cursor() as cur:
        cur.execute(
            "SELECT id AS team_id, name AS team, token FROM teams WHERE id = %s",
            (team_id,),
        )
        team = cur.fetchone()
    if not team:
        raise HTTPException(status_code=404, detail="Tim tidak ditemukan.")
    return dict(team)


@app.get("/admin/")
def admin_index():
    admin_index_path = os.path.join(REACT_FRONTEND, "admin", "index.html")
    if not os.path.isfile(admin_index_path):
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard build is unavailable.",
        )
    return FileResponse(admin_index_path)


app.mount(
    "/assets",
    OptionalStaticFiles(
        directory=os.path.join(REACT_FRONTEND, "assets"),
        check_dir=False,
    ),
    name="react-assets",
)
