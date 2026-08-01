#!/usr/bin/env bash
# Backup → drop → restore roundtrip for the repave Postgres durable store.
# Used by make postgres-dr-drill and documented in docs/operations/postgres-backup-restore.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONTAINER_NAME="${POSTGRES_DR_DRILL_CONTAINER:-repave-postgres-dr-drill}"
PORT="${POSTGRES_DR_DRILL_PORT:-54329}"
USE_DOCKER="${POSTGRES_DR_DRILL_DOCKER:-1}"
DATABASE_URL="${REPAVE_DATABASE_URL:-postgresql://repave:repave@127.0.0.1:${PORT}/repave}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required" >&2
    exit 1
  fi
}

cleanup() {
  if [[ "${POSTGRES_DR_DRILL_KEEP:-}" == "1" || "${USE_DOCKER}" != "1" ]]; then
    return 0
  fi
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

wait_postgres() {
  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    if [[ "${USE_DOCKER}" == "1" ]]; then
      if docker exec "${CONTAINER_NAME}" pg_isready -U repave >/dev/null 2>&1; then
        return 0
      fi
    elif command -v pg_isready >/dev/null 2>&1 && pg_isready -d "${REPAVE_DATABASE_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for Postgres" >&2
  return 1
}

pg_admin() {
  if [[ "${USE_DOCKER}" == "1" ]]; then
    docker exec "${CONTAINER_NAME}" psql -U repave -d postgres -v ON_ERROR_STOP=1 "$@"
  else
    psql "${ADMIN_URL}" -v ON_ERROR_STOP=1 "$@"
  fi
}

pg_dump_backup() {
  local dest="$1"
  if [[ "${USE_DOCKER}" == "1" ]]; then
    docker exec "${CONTAINER_NAME}" pg_dump -Fc -U repave repave >"${dest}"
  else
    pg_dump -Fc "${REPAVE_DATABASE_URL}" -f "${dest}"
  fi
}

pg_restore_backup() {
  local src="$1"
  if [[ "${USE_DOCKER}" == "1" ]]; then
    docker exec -i "${CONTAINER_NAME}" pg_restore -U repave -d repave --no-owner --role=repave <"${src}" || true
  else
    pg_restore -d "${REPAVE_DATABASE_URL}" --no-owner --role=repave "${src}" || true
  fi
}

seed_fixture() {
  cd "${ROOT}/engine"
  uv run python <<'PY'
import json
import os
from datetime import UTC, datetime

from repave_engine.sql_store import connect, ensure_schema, parse_database_url

config = parse_database_url(os.environ["REPAVE_DATABASE_URL"], repo_root=os.environ["REPAVE_ROOT"])
conn = connect(config)
ensure_schema(conn)
now = datetime.now(UTC).replace(microsecond=0).isoformat()
conn.execute(
    """
    INSERT INTO runs (
        run_id, status, blueprint_name, dry_run, acting_user,
        created_at, updated_at, payload_json
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (run_id) DO NOTHING
    """,
    ("dr-drill-run", "succeeded", "dr-drill", 1, "dr-drill", now, now, "{}"),
)
conn.execute(
    "INSERT INTO audit_events (record_json, created_at) VALUES (%s, %s)",
    (json.dumps({"event": "dr-drill", "ts": now}), now),
)
conn.commit()
conn.close()
PY
}

count_tables() {
  cd "${ROOT}/engine"
  uv run python <<'PY'
import os

from repave_engine.sql_store import connect, parse_database_url

config = parse_database_url(os.environ["REPAVE_DATABASE_URL"], repo_root=os.environ["REPAVE_ROOT"])
conn = connect(config)
for table in (
    "runs",
    "run_events",
    "audit_events",
    "fleet_events",
    "publish_receipts",
    "sessions",
):
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    print(f"COUNT {table}={row['c']}")
conn.close()
PY
}

collect_counts() {
  COUNT_LINES=()
  while IFS= read -r line; do
    COUNT_LINES+=("$line")
  done < <(count_tables)
}

trap cleanup EXIT

require docker

if [[ "${USE_DOCKER}" != "1" ]]; then
  require pg_dump
  require pg_restore
  require psql
fi

if [[ "${USE_DOCKER}" == "1" ]]; then
  echo "==> ephemeral postgres:16-alpine on port ${PORT}"
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker run -d --name "${CONTAINER_NAME}" \
    -e POSTGRES_USER=repave \
    -e POSTGRES_PASSWORD=repave \
    -e POSTGRES_DB=repave \
    -p "${PORT}:5432" \
    postgres:16-alpine >/dev/null
  DATABASE_URL="postgresql://repave:repave@127.0.0.1:${PORT}/repave"
  wait_postgres
fi

export REPAVE_DATABASE_URL="${DATABASE_URL}"
export REPAVE_ROOT="${ROOT}"

echo "==> seed schema + fixture rows"
seed_fixture
collect_counts
SEED_COUNTS=("${COUNT_LINES[@]}")
printf '%s\n' "${SEED_COUNTS[@]}"

DUMP="$(mktemp -t repave-pg-drill.XXXXXX.dump)"
echo "==> pg_dump -Fc"
pg_dump_backup "${DUMP}"

ADMIN_URL="${REPAVE_DATABASE_URL%/*}/postgres"
echo "==> drop and recreate repave database"
pg_admin -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'repave' AND pid <> pg_backend_pid();" >/dev/null || true
pg_admin -c "DROP DATABASE IF EXISTS repave;"
pg_admin -c "CREATE DATABASE repave OWNER repave;"
wait_postgres

echo "==> pg_restore"
pg_restore_backup "${DUMP}"

echo "==> verify row counts after restore"
collect_counts
RESTORE_COUNTS=("${COUNT_LINES[@]}")
if [[ "${#SEED_COUNTS[@]}" -ne "${#RESTORE_COUNTS[@]}" ]]; then
  echo "count line mismatch after restore" >&2
  exit 1
fi
for i in "${!SEED_COUNTS[@]}"; do
  if [[ "${SEED_COUNTS[$i]}" != "${RESTORE_COUNTS[$i]}" ]]; then
    echo "mismatch: ${SEED_COUNTS[$i]} vs ${RESTORE_COUNTS[$i]}" >&2
    exit 1
  fi
done

rm -f "${DUMP}"
echo "OK: postgres DR drill passed (${REPAVE_DATABASE_URL})"
