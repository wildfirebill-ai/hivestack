#!/usr/bin/env bash
# hivestack — periodic maintenance: VACUUM the SQLite DB then write a dated
# backup to /data/backups. Launched as a background loop from the entrypoint.
#   HIVESTACK_MAINT_INTERVAL_SECONDS (default 86400 = daily)
set -euo pipefail

DATA_DIR="${HIVESTACK_DATA_DIR:-/data}"
CONFIG_DIR="${HIVESTACK_CONFIG_DIR:-/config}"
DB="${DATA_DIR}/hivestack.db"
BACKUP_DIR="${DATA_DIR}/backups"
INTERVAL="${HIVESTACK_MAINT_INTERVAL_SECONDS:-86400}"

log() { echo "[hivestack:maintenance] $*"; }

run_once() {
  mkdir -p "${BACKUP_DIR}"
  # 1) VACUUM (WAL checkpoint + reclaim space + rebuild indexes)
  if [[ -f "${DB}" ]]; then
    if python - <<PY
import sqlite3, sys
con = sqlite3.connect("${DB}", timeout=10)
try:
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("VACUUM")
    print("vacuumed ok")
except Exception as e:
    print("vacuum failed:", e, file=sys.stderr)
    sys.exit(1)
PY
    then
      log "VACUUM ok"
    else
      log "VACUUM failed — skipping backup this cycle"
      return 1
    fi
  else
    log "no DB yet (${DB}) — skipping VACUUM"
  fi

  # 2) dated backup
  if python /app/scripts/backup.py --data "${DATA_DIR}" --config "${CONFIG_DIR}" --out "${BACKUP_DIR}"; then
    # prune old backups, keep the most recent N
    keep="${HIVESTACK_BACKUP_KEEP:-7}"
    ls -1t "${BACKUP_DIR}"/hivestack-backup-*.zip 2>/dev/null | tail -n +$((keep + 1)) | xargs -r rm -f
    log "backup + prune ok (keep ${keep})"
  else
    log "backup failed"
  fi
}

log "maintenance service started (interval ${INTERVAL}s)"
while true; do
  run_once || true
  sleep "${INTERVAL}"
done
