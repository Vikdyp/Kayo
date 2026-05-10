#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/srv/kayo}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-master}"
BACKUP_SERVICE="${BACKUP_SERVICE:-kayo-postgres-backup.service}"
SKIP_BACKUP="${SKIP_BACKUP:-0}"

cd "${APP_DIR}"

if [ ! -d .git ]; then
  echo "ERROR: ${APP_DIR} is not a Git checkout." >&2
  exit 1
fi

if [ ! -f docker-compose.yml ]; then
  echo "ERROR: docker-compose.yml not found in ${APP_DIR}." >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: tracked files are modified in ${APP_DIR}; commit, stash, or restore them before deploy." >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

before_sha="$(git rev-parse --short HEAD)"

git fetch --prune "${REMOTE}" "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only "${REMOTE}" "${BRANCH}"

after_sha="$(git rev-parse --short HEAD)"

docker compose config -q

if [ "${SKIP_BACKUP}" != "1" ] && systemctl list-unit-files "${BACKUP_SERVICE}" >/dev/null 2>&1; then
  systemctl start "${BACKUP_SERVICE}"
fi

docker compose up -d --build bot
docker compose ps
docker exec kayo-bot python tools/smoke_runtime.py --skip-migrations

echo "Deployed ${before_sha} -> ${after_sha}"
docker logs --since 5m kayo-bot 2>&1 | grep -Ei 'error|exception|traceback|failed|critical' || true
