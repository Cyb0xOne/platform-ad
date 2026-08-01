#!/bin/bash
# Forced command for the ForcAD lifecycle control channel.
#
# The admin listener reaches this over SSH with the desired action as the sole
# SSH_ORIGINAL_COMMAND. That value is compared by EXACT string equality against a
# three-element allowlist and is NEVER parsed, split, evaluated, or passed to a
# shell — so "start; reset", "start --fast --build", newlines, etc. all fall to
# the deny arm. Install as the forced command in authorized_keys (see README.md).
set -euo pipefail

# Non-interactive SSH on this host has an EMPTY PATH and docker lives in /usr/sbin,
# so set an explicit PATH. control.py (via utils.run_docker) inherits this env.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin

FORCAD="${FORCAD_DIR:-$HOME/adlab/forcad}"
PY="${FORCAD_PY:-$FORCAD/.venv/bin/python}"

case "${SSH_ORIGINAL_COMMAND:-}" in
  start)  set -- start --fast ;;
  pause)  set -- pause ;;
  resume) set -- resume ;;
  *) echo "denied: only start|pause|resume are permitted" >&2; exit 64 ;;
esac

cd "$FORCAD"
# ponytail: one global lock — the actions are host-wide, so per-action locks buy
# nothing. flock -E 75 makes "another action in flight" (75) distinct from a
# propagated control.py failure (1).
exec flock -n -E 75 "$HOME/.adlab-control.lock" "$PY" control.py "$@"
