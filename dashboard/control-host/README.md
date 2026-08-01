# ForcAD control channel (host side)

`forcad-control.sh` is an SSH **forced command**: it lets the loopback-only admin
listener trigger exactly three ForcAD lifecycle actions on the Docker host, with
no shell access and no other commands reachable.

## What it allows

| SSH_ORIGINAL_COMMAND | Runs | Exit |
|---|---|---|
| `start`  | `control.py start --fast` | control.py's exit |
| `pause`  | `control.py pause`  | control.py's exit |
| `resume` | `control.py resume` | control.py's exit |
| anything else | nothing | `64` (denied) |
| another action already running | nothing | `75` (busy, via `flock`) |

The action string is matched by exact equality — it is never parsed or passed to
a shell, so `start; reset`, `start --fast --build`, trailing spaces, alternate
casing, and embedded newlines are all denied. `reset`, `clean`, `setup`, `build`,
and any generic `docker compose` passthrough are intentionally unreachable.

`control.py` writes its human-readable output to **stderr**, so callers must judge
success by the exit code, never by stderr being non-empty.

## Install

Copy the wrapper to the host (outside any container mount), owned by the host
user and not writable by the admin container:

```sh
install -m 0755 forcad-control.sh "$HOME/adlab/control-host/forcad-control.sh"
```

Add a dedicated key to `~/.ssh/authorized_keys` pinned to the forced command.
`restrict` disables PTY allocation and all forwarding:

```
restrict,command="/home/reky/adlab/control-host/forcad-control.sh" ssh-ed25519 AAAA...adlab-control
```

The admin container mounts the matching private key read-only and connects as
`reky@host.docker.internal`, sending only the bare action word. `reky` is already
in the `docker` group, so no `sudo` is involved anywhere.

## Overrides (used by the tests)

- `FORCAD_DIR` — ForcAD checkout (default `$HOME/adlab/forcad`).
- `FORCAD_PY` — interpreter (default `$FORCAD_DIR/.venv/bin/python`).

## Test

```sh
./test-forcad-control.sh
```

Runs the wrapper against a fake `control.py` in a temp dir — translation,
the full rejection table, failure propagation, and lock contention — without
touching real infrastructure.
