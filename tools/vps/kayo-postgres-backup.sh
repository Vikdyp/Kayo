#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${KAYO_PROJECT_DIR:-/srv/kayo}"
BACKUP_DIR="${KAYO_BACKUP_DIR:-/srv/kayo/backups/postgres}"
RETENTION_DAYS="${KAYO_BACKUP_RETENTION_DAYS:-14}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [ ! -f "${PROJECT_DIR}/docker-compose.yml" ]; then
  echo "docker-compose.yml not found in ${PROJECT_DIR}" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp_file="${BACKUP_DIR}/kayo-postgres-${timestamp}.dump.tmp"
backup_file="${BACKUP_DIR}/kayo-postgres-${timestamp}.dump"
checksum_file="${backup_file}.sha256"

cleanup() {
  rm -f "${tmp_file}"
}
trap cleanup EXIT

cd "${PROJECT_DIR}"

docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${tmp_file}"

if [ ! -s "${tmp_file}" ]; then
  echo "backup file is empty" >&2
  exit 1
fi

mv "${tmp_file}" "${backup_file}"
sha256sum "${backup_file}" > "${checksum_file}"
chmod 600 "${backup_file}" "${checksum_file}"

find "${BACKUP_DIR}" -type f \
  \( -name 'kayo-postgres-*.dump' -o -name 'kayo-postgres-*.dump.sha256' \) \
  -mtime +"${RETENTION_DAYS}" \
  -delete

echo "created ${backup_file}"
