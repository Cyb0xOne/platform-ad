# Cutover Runbook — React dashboard + secure admin listener

> **STATUS: NOT EXECUTED.** This documents the irreversible production steps for
> the migration. Every step here runs on the server `reky@192.168.43.136` and/or
> mutates live competition state. Do not run any of it without an explicit
> decision to cut over. Nothing in this repo has been committed yet.

## Preconditions (must all be true before step 1)
- [ ] Changeset committed and pushed to the deploy remote (git-driven deploy).
- [ ] Server reachable: `ssh reky@192.168.43.136` (non-interactive shell has an
      empty PATH — scripts must set PATH or use `bash -lc`).
- [ ] `dashboard/.env` present on server with `FORCAD_DSN=...` (never committed).
- [ ] `dashboard/secrets/vmkey` (vulnbox SSH key) present, mode `600`.
- [ ] `dashboard/secrets/controlkey` (ForcAD control key) present, mode `600`,
      and its public half installed on the host `~/.ssh/authorized_keys` as a
      forced command per `dashboard/control-host/README.md`:
      `restrict,command="/home/reky/adlab/control-host/forcad-control.sh" ssh-ed25519 AAAA...adlab-control`
- [ ] `dashboard/control-host/forcad-control.sh` copied to
      `~/adlab/control-host/forcad-control.sh`, owned by `reky`, mode `0755`,
      NOT inside any container mount.
- [ ] External docker network `forcad_default` exists (ForcAD is up).

## Steps

### 1. Build + start both listeners (reversible)
```sh
cd ~/adlab/dashboard   # wherever the repo lives on the server
docker compose build
docker compose up -d
```
Public UI -> `http://<server>:8090` (legacy `/` by default). Admin listener ->
loopback only `127.0.0.1:8091` (reach via SSH tunnel:
`ssh -L 8091:127.0.0.1:8091 reky@192.168.43.136`).

### 2. Smoke (reversible)
```sh
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/        # 200 (legacy)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/next/   # 200 (React public)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/admin/  # 404 (isolation)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/admin/  # 200 (admin console, via tunnel)
```

### 3. Rotate exposed team tokens — **IRREVERSIBLE, coordinate with teams**
Tokens were reachable on the pre-Phase-0 public scoreboard. Rotate them in the
ForcAD engine (invalidates every team's current token — do this in a maintenance
window and redistribute new tokens). This is a ForcAD/DB operation, not a
dashboard one; use the engine's supported path. Re-verify the public scoreboard
no longer exposes any token afterward.

### 4. ForcAD lifecycle rehearsal via admin console (reversible)
Through the tunnel at `127.0.0.1:8091/admin/`, exercise on a throwaway round:
`pause` -> confirm ticker/flag-intake stop -> `resume` -> confirm resume ->
`start` only if a (re)start is actually intended. Confirm each appears in the
operation history with outcome `ok`. The wrapper allows ONLY these three; nothing
else is reachable.

### 5. Flip default UI (reversible — this is the actual "cutover")
When confident, in `dashboard/.env`:
```sh
echo "DASHBOARD_DEFAULT_UI=react" >> .env
docker compose up -d dashboard   # recreate public listener
```
`/` now serves React. **Rollback:** remove that line (or set `legacy`) and
`docker compose up -d dashboard`; `/legacy/` also always serves the old UI.

## Rollback summary
- UI: unset `DASHBOARD_DEFAULT_UI` (default legacy) or hit `/legacy/`.
- Containers: `docker compose down` (both) or `docker compose restart`.
- Token rotation (step 3) is the only step with NO rollback — teams keep the new
  tokens.
