#!/bin/sh
# Container entrypoint: make the (root-owned) mounted /data volume writable by
# the unprivileged app user, then drop privileges and exec the server.
#
# /data holds two durable things: the settlement ledger (revenue/audit trail +
# replay idempotency for real x402 charges) and ingest sessions (a buyer's paid
# ingest must survive a redeploy so their later mine/pack calls still work).
# Docker mounts volumes root-owned, but the app runs as `appuser` (non-root
# hardening). We start as root ONLY to fix ownership, then `gosu appuser`.
set -e

LEDGER_PATH="${LEDGER_PATH:-/data/ledger.db}"
LEDGER_DIR="$(dirname "$LEDGER_PATH")"
SESSION_DIR="${CC_SESSION_DIR:-/data/sessions}"

for dir in "$LEDGER_DIR" "$SESSION_DIR"; do
  case "$dir" in
    /*)
      mkdir -p "$dir"
      chown -R appuser:appuser "$dir" 2>/dev/null || true
      ;;
  esac
done

# Drop root and exec the server as appuser (replaces PID 1; signals propagate).
exec gosu appuser "$@"
