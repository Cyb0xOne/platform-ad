# Task 11 — `mediocre` (:1980, DSM-11 MUMPS): SPIKE BLOCKED

**Status:** BLOCKED (best-effort spike per brief §Risiko / Step 3). Does **not** block Tasks 1–10/12.
No `checker.py` written. `config.enowars10.yml` **not** touched. No live transcript — the service
could not be booted (see blocker). This file is the Step-3 stuck-path deliverable.

**Date:** 2026-07-27 · **Branch:** `enowars10-checkers`

---

## 1. Blocker (verified) — service disk images are absent everywhere

The `mediocre` repo ships only the **deploy harness**, never the DSM-11 payload. Three disk images
are referenced by the SIMH configs but exist nowhere:

| Image | Referenced by | Holds |
|---|---|---|
| `terminal-server.dsk` | `terminal.ini:6` (`attach rl0`) | DSM-11 OS for the 8 terminal login nodes |
| `storage-server.dsk`  | `storage.ini:5` (`attach rl0`) | DSM-11 OS for the storage node |
| `data.dsk`            | `storage.ini:7` (`attach hk0`) | The shared MUMPS **global** volume (DM0) — the medical-records app **and where flags live** |

Verification matrix (all negative):

- Repo working tree — `find … -iname '*.dsk'` → none (only `deploy/`, `docker-compose.yml`, `.env`, `DO_NOT_TOUCH_THIS.md`).
- Git — `git ls-files '*.dsk'` empty; `git log --all -- '*.dsk'` empty; no LFS (`git lfs ls-files` empty, no `filter=lfs` in any `.gitattributes`); `git status --ignored` shows no ignored `.dsk`/`state/`.
- Workspace — `find /home/reky/workspaces/cylab/ctf -iname '*.dsk*'` → none.
- Server (`192.168.43.136`) — `~/adlab/eno10/mediocre` not staged; `find ~/adlab -iname '*.dsk*'` → none; `docker images` has no `mediocre`/`simh`.
- No fetch mechanism — `Dockerfile` builds SIMH **from source** (git clone open-simh + `simh.patch` + cmake/ninja) but never provides a disk; no setup/download/make script; `.env` is only `COMPOSE_PROJECT_NAME=mediocre`.
- Operator (repo owner) confirmed on 2026-07-27 they have no access to the images.

## 2. Why this hard-blocks the spike

`docker-compose.yml` bind-mounts `./state/<node>:/sim/state` **over** the image's `/sim/state`, and
the `.ini` files `attach` the disks by relative path from that dir (WORKDIR `/sim/state`). A fresh
`./state/` is empty, so `attach rl0 terminal-server.dsk` finds nothing → SIMH never boots DSM-11 →
haproxy `:1980` has no healthy `terminal-N:1337` backend → no login prompt → **the entire brief is
unreachable**: Step 1 (live telnet recon of login + a MUMPS global put/get) cannot start, so Steps
2–3 (write + gate checker) cannot follow. A checker for this service is impossible to author or
validate without a running instance carrying the real app + flag globals.

## 3. Architecture recon completed (source-level — reuse this, don't re-derive)

Fully mapped from source this session; a future attempt with images can skip straight to §4.

**Topology (11 containers, one shared image `mediocre-simh:latest` + stock `haproxy:alpine`):**
- `vde` — `vde_switch` on unix sock `/vde/dsm_switch` (mode 0700), the virtual Ethernet fabric. All SIMH nodes attach their DEUNA (`xu`) here.
- `storage` — PDP-11/44 DSM-11 with an **extra** `data.dsk` on HK (`attach hk0 data.dsk`), boot-mounted **DM0 for access via `D` (DDP)** → serves the shared globals over VDE. No telnet login line; console proxy on `127.0.0.1:4100` only.
- `terminal-1..8` — PDP-11/44 DSM-11, DDP **client** enabled at boot; each presents a login on SIMH `vh` (DHU11) TCP line **:1337**. Console proxy on `127.0.0.1:410N`.
- `haproxy` — `mode tcp`, `balance roundrobin` over `terminal-1..8:1337`, frontend `bind *:1980` (published `1980:1980`, **all interfaces**; terminals/storage ports are `127.0.0.1`-only).

**Two-port model (important — don't confuse them):**
- `SIM_PORT` (4100 storage, 4101–4108 terminals) = `sim-runner.py`'s TCP↔PTY proxy to the **SIMH
  simulator console** (boot output, `sim>` control). 127.0.0.1-only. This is the path whose telnet
  IAC is scrubbed by `sim-runner.telnet_clean` + `TELNET_PREAMBLE`. **Not** the checker path.
- `:1337` = SIMH's **own** `vh` DHU11 telnet line = the **DSM-11 guest login**. haproxy `:1980`→
  `:1337`. The checker talks here, so it faces **SIMH-native `vh` telnet IAC**, not sim-runner's
  cleaner. → the live recon must capture the real IAC bytes on `:1980`; `A.LineClient` (raw socket)
  is the right tool, likely needing to swallow/answer an initial IAC burst.

**Round-robin safety:** every `put`/`get` may land on a different terminal, but all terminals reach
the same globals on `storage`'s DM0 volume via DDP over VDE. So put-on-t3 / get-on-t5 is safe — the
core correctness property the checker relies on. (Confirmed from `storage.ini` DDP mount + terminal
`Startup Distributed Database Processing → Y`.)

**Boot automation:** `terminal.ini` / `storage.ini` `expect`/`send` rules auto-answer DSM-11
**boot** prompts (date/time, "Start up the default system", DDP, Caretaker, disk mounts). SIMH is
patched (`simh.patch`, applied at build): VDE sock 0700, `SO_REUSEADDR`, poll-every-call +
round-robin line assignment, DSM-11 idle-loop → `sim_idle()`, DHU11 spawn-on-connect carrier-edge
fix. `set cpu idle` keeps CPU cheap when idle.

**Build:** multi-stage `debian:bookworm-slim`; builder clones `open-simh@7994e0a…`, `git apply
simh.patch`, cmake/ninja builds the `pdp11` target; runtime copies the binary + `vde2`/`python3`/SDL
libs. **No `RUN --mount=type=cache`** anywhere → builds clean on the server (same as Tasks 8–10),
but it's a from-source SIMH compile → expect a **slow first build** (needs internet: git + apt).

**Resource envelope:** mem_limits ≈ 8×256m (terminals) + 256m (storage) + 64m (vde) + 64m (haproxy)
≈ **2.4 GB**; cpus ≈ 3.7. Fits the 8c/15GB server (measured 6.4 GiB free, idle load) — bring other
eno services down if RAM tightens. Terminals have `start_period: 90s` (SIMH cold boot); haproxy
`depends_on` all 8 healthy → **full readiness ~90s+**.

## 4. Deploy runbook (run once real images exist)

1. Place the three images so the bind mounts see them: `./state/storage/{storage-server.dsk,data.dsk}`,
   and `./state/terminal-N/terminal-server.dsk` for N=1..8 (each terminal has its own `./state/terminal-N`
   mount; confirm whether they can share one OS image copy or each needs its own — the compose gives
   each terminal a **separate** state dir, so copy `terminal-server.dsk` into all 8).
2. `rsync` the `mediocre/` tree → server `~/adlab/eno10/mediocre/` (exclude `.git`; **include** the
   populated `state/`). Server SSH gotcha: login shell is **zsh with empty PATH** — prefix remote
   commands with `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin;` (the
   handoff's "`bash -lc`" fails — bash isn't on the empty PATH). Docker is `/usr/sbin/docker`.
3. `docker compose build` (slow, from-source SIMH) then `docker compose up -d`.
4. Wait ≥90–120s; check `docker compose ps` all healthy and `docker logs` for a DSM-11 login banner.
5. Recon from laptop directly to `192.168.43.136:1980` while host-published (matches Task 10 flow).
6. For gating: `docker network connect forcad_default mediocre-haproxy-1`, gate the 5 mandatory cases
   from inside `forcad-celery-1` (`docker exec`, user `nobody`) against haproxy's `forcad_default` IP
   on :1980. Teardown `docker compose down -v` after (RAM discipline).

## 5. Live recon still required (Step 1 of brief — blocked until §4)

- Exact **IAC handshake** bytes on `:1980` (SIMH `vh` telnet) and whether `LineClient` must answer WILL/DO.
- The **login flow**: prompt text (recon banked `"Username: "`), what a normal login is, and what it
  drops you into — a DSM-11 app menu (medical records) or a raw MUMPS `>` prompt.
- `MGR:xxx` per `DO_NOT_TOUCH_THIS.md` "didn't work on public access" → that's the privileged/attacker
  path, **not** the checker path. Find the legitimate store/retrieve flow.
- The concrete **put/get commands** + the **global name/record key** to store a flag and read it back.
- Data TTL / reaper behaviour (does a record survive long enough between put and get rounds?).

## 6. Proposed checker design (contingent on §5)

`put`: `LineClient` → :1980 → login → create a medical record (or `S ^GLOBAL(id)=flag` if a MUMPS
prompt is reachable) → return record key as `flag_id`/state. `get`: login → read record by key →
`assert_in(flag)`. `check`: connect + confirm login banner (liveness). Classify with narrow, named
excepts → MUMBLE on protocol refusal, DOWN on connect/timeout; never `except Exception` (swallows
`CheckFinished`). Round-robin is safe (DDP shared store), so no terminal affinity needed.

## 7. To unblock

Obtain the **ENOWARS `mediocre` vulnbox disk images** (organizer service release / the actual
vulnbox the team defends). Drop them per §4 step 1, then §4 is executable end-to-end. A **generic
vintage DSM-11 image will not substitute** — the checker must exercise *this* service's
medical-records app and its specific flag globals, which only the ENOWARS payload contains.

## 8. Config note (deferred — do not apply until gate passes)

The brief wants `checker_timeout: 40` for `mediocre`. Current `forcad/config.enowars10.yml` uses
`round_time: 120`, which satisfies `round_time ≥ 4× max_checker_timeout` only up to 30 (overeats).
Adding mediocre@40 forces `round_time ≥ 160`, which then breaks the reaper budget
`round_time × flag_lifetime ≤ ~720s` at `flag_lifetime: 5` (160×5=800) → `flag_lifetime` must drop
to ≤4. Only touch config if/when the gate passes (brief Step 3).
