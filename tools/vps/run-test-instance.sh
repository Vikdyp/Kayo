#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR_WAS_SET="${APP_DIR+x}"
APP_DIR="${APP_DIR:-/srv/kayo}"
PROD_CONTAINER="${PROD_CONTAINER:-kayo-bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-kayo-postgres}"
TEST_CONTAINER="${TEST_CONTAINER:-kayo-bot-test}"
TEST_IMAGE_REPO="${TEST_IMAGE_REPO:-kayo-bot-test}"
TEST_WORKTREE_PREFIX="${TEST_WORKTREE_PREFIX:-/tmp/kayo-test}"

usage() {
  cat <<'EOF'
Usage:
  tools/vps/run-test-instance.sh start [--copy-prod-db] [--ref REF]
  tools/vps/run-test-instance.sh status
  tools/vps/run-test-instance.sh logs [--since DURATION] [--tail LINES] [--errors]
  tools/vps/run-test-instance.sh cleanup [--drop-test-db]

Environment overrides:
  APP_DIR=/srv/kayo
  PROD_CONTAINER=kayo-bot
  POSTGRES_CONTAINER=kayo-postgres
  TEST_CONTAINER=kayo-bot-test
  TEST_IMAGE_REPO=kayo-bot-test
  TEST_WORKTREE_PREFIX=/tmp/kayo-test
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

require_app_dir() {
  if [ -z "${APP_DIR_WAS_SET}" ] && [ "${APP_DIR}" != "/srv/kayo" ]; then
    die "APP_DIR default must be /srv/kayo"
  fi
  [ -d "${APP_DIR}" ] || die "APP_DIR not found: ${APP_DIR}"
  [ -d "${APP_DIR}/.git" ] || die "${APP_DIR} is not a Git checkout"
  [ -f "${APP_DIR}/docker-compose.yml" ] || die "docker-compose.yml not found in ${APP_DIR}"
  [ -f "${APP_DIR}/.env" ] || die ".env not found in ${APP_DIR}"
}

require_clean_checkout() {
  local dirty
  dirty="$(git -C "${APP_DIR}" status --porcelain --untracked-files=no)"
  if [ -n "${dirty}" ]; then
    echo "${dirty}" >&2
    die "tracked files are modified in ${APP_DIR}; commit, stash, or restore them first"
  fi
}

read_env() {
  local key="$1"
  grep -E "^${key}=" "${APP_DIR}/.env" | tail -n 1 | cut -d= -f2- | tr -d '\r'
}

require_env_value() {
  local key="$1"
  local value
  value="$(read_env "${key}" || true)"
  [ -n "${value}" ] || die "${key} is missing or empty in ${APP_DIR}/.env"
  printf '%s' "${value}"
}

prod_db_name() {
  require_env_value DATABASE_NAME
}

test_db_name() {
  require_env_value DATABASE_TEST_NAME
}

guard_test_db_name() {
  local prod_db="$1"
  local test_db="$2"
  [ -n "${prod_db}" ] || die "production database name is empty"
  [ -n "${test_db}" ] || die "test database name is empty"
  [ "${prod_db}" != "${test_db}" ] || die "DATABASE_TEST_NAME must differ from DATABASE_NAME"
}

postgres_is_running() {
  docker inspect -f '{{.State.Running}}' "${POSTGRES_CONTAINER}" 2>/dev/null | grep -qx true
}

database_exists() {
  local db_name="$1"
  docker exec -e DB_NAME="${db_name}" "${POSTGRES_CONTAINER}" sh -c \
    'psql -U "$POSTGRES_USER" -d postgres -Atc "select datname from pg_database" | grep -qx "$DB_NAME"'
}

copy_prod_db_to_test() {
  local prod_db="$1"
  local test_db="$2"
  guard_test_db_name "${prod_db}" "${test_db}"
  postgres_is_running || die "${POSTGRES_CONTAINER} is not running"

  info "Recreating ${test_db} from ${prod_db}"
  docker exec -e SRC_DB="${prod_db}" -e TEST_DB="${test_db}" "${POSTGRES_CONTAINER}" sh -c '
    set -eu
    dump=/tmp/kayo-test-db-copy.dump
    rm -f "$dump"
    pg_dump -U "$POSTGRES_USER" -d "$SRC_DB" -Fc --no-owner --no-privileges -f "$dump"
    dropdb --if-exists --force -U "$POSTGRES_USER" "$TEST_DB"
    createdb -U "$POSTGRES_USER" "$TEST_DB"
    pg_restore -U "$POSTGRES_USER" -d "$TEST_DB" --no-owner --no-privileges "$dump"
    rm -f "$dump"
  '
}

drop_test_db() {
  local prod_db="$1"
  local test_db="$2"
  guard_test_db_name "${prod_db}" "${test_db}"
  postgres_is_running || die "${POSTGRES_CONTAINER} is not running"

  info "Dropping ${test_db}"
  docker exec -e TEST_DB="${test_db}" "${POSTGRES_CONTAINER}" sh -c \
    'dropdb --if-exists --force -U "$POSTGRES_USER" "$TEST_DB"'
}

test_network_name() {
  docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    "${POSTGRES_CONTAINER}" | head -n 1
}

container_exists() {
  docker inspect "$1" >/dev/null 2>&1
}

cmd_start() {
  local copy_prod_db=0
  local ref="HEAD"

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --copy-prod-db)
        copy_prod_db=1
        shift
        ;;
      --ref)
        [ "$#" -ge 2 ] || die "--ref requires a value"
        ref="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown start option: $1"
        ;;
    esac
  done

  require_app_dir
  require_command docker
  require_command git
  require_clean_checkout

  [ -n "$(require_env_value DISCORD_TOKEN_TEST)" ] || exit 1
  [ -n "$(require_env_value TEST_GUILD_ID)" ] || exit 1
  local prod_db
  local test_db
  prod_db="$(prod_db_name)"
  test_db="$(test_db_name)"
  guard_test_db_name "${prod_db}" "${test_db}"
  postgres_is_running || die "${POSTGRES_CONTAINER} is not running"
  container_exists "${TEST_CONTAINER}" && die "${TEST_CONTAINER} already exists; run cleanup first"

  if [ "${copy_prod_db}" = "1" ]; then
    copy_prod_db_to_test "${prod_db}" "${test_db}"
  elif ! database_exists "${test_db}"; then
    die "${test_db} does not exist; rerun with --copy-prod-db or create it manually"
  fi

  local run_id
  local worktree
  local image
  local network
  run_id="$(date -u +%Y%m%dT%H%M%SZ)"
  worktree="$(mktemp -d "${TEST_WORKTREE_PREFIX}-${run_id}-XXXXXX")"
  image="${TEST_IMAGE_REPO}:${run_id}"

  info "Creating worktree ${worktree} from ${ref}"
  git -C "${APP_DIR}" worktree add --detach "${worktree}" "${ref}"

  info "Building ${image}"
  docker build -t "${image}" "${worktree}"

  network="$(test_network_name)"
  [ -n "${network}" ] || die "could not resolve Docker network for ${POSTGRES_CONTAINER}"

  info "Starting ${TEST_CONTAINER} on ${network}"
  docker run -d \
    --name "${TEST_CONTAINER}" \
    --network "${network}" \
    --env-file "${APP_DIR}/.env" \
    -e TEST_MODE=true \
    -e DATABASE_HOST=postgres \
    -e DATABASE_PORT=5432 \
    -e DATABASE_SSL=false \
    -e DATABASE_TEST_NAME="${test_db}" \
    --label kayo.temporary=test-instance \
    --label kayo.worktree="${worktree}" \
    --label kayo.image="${image}" \
    --label kayo.run_id="${run_id}" \
    "${image}" \
    python bot.py

  echo
  echo "Started ${TEST_CONTAINER}"
  echo "Image: ${image}"
  echo "Worktree: ${worktree}"
  echo "Database: ${test_db}"
  echo "Next: tools/vps/run-test-instance.sh logs --since 2m"
}

print_container_status() {
  local name="$1"
  if container_exists "${name}"; then
    docker inspect -f 'container={{.Name}} status={{.State.Status}} running={{.State.Running}} image={{.Config.Image}}' "${name}"
  else
    echo "container=/${name} status=absent"
  fi
}

cmd_status() {
  require_app_dir
  require_command docker
  require_command git

  local prod_db
  local test_db
  prod_db="$(prod_db_name)"
  test_db="$(test_db_name)"
  guard_test_db_name "${prod_db}" "${test_db}"

  echo "APP_DIR=${APP_DIR}"
  echo "Git:"
  git -C "${APP_DIR}" status --short --branch
  git -C "${APP_DIR}" rev-parse --short HEAD

  echo
  echo "Containers:"
  print_container_status "${PROD_CONTAINER}"
  print_container_status "${POSTGRES_CONTAINER}"
  print_container_status "${TEST_CONTAINER}"

  echo
  echo "Test images:"
  docker images --format 'image={{.Repository}}:{{.Tag}} id={{.ID}} created={{.CreatedSince}}' "${TEST_IMAGE_REPO}" || true

  echo
  echo "Test worktrees:"
  git -C "${APP_DIR}" worktree list | grep "${TEST_WORKTREE_PREFIX}" || echo "none"

  echo
  echo "Test database:"
  if postgres_is_running && database_exists "${test_db}"; then
    echo "${test_db}=present"
  else
    echo "${test_db}=absent"
  fi
}

cmd_logs() {
  local since="10m"
  local tail_lines="200"
  local errors_only=0

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --since)
        [ "$#" -ge 2 ] || die "--since requires a value"
        since="$2"
        shift 2
        ;;
      --tail)
        [ "$#" -ge 2 ] || die "--tail requires a value"
        tail_lines="$2"
        shift 2
        ;;
      --errors)
        errors_only=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown logs option: $1"
        ;;
    esac
  done

  require_command docker
  container_exists "${TEST_CONTAINER}" || die "${TEST_CONTAINER} does not exist"

  if [ "${errors_only}" = "1" ]; then
    docker logs --since "${since}" --tail "${tail_lines}" "${TEST_CONTAINER}" 2>&1 \
      | grep -Ei 'error|exception|traceback|failed|critical|Synced globally|Synced to test guild' || true
  else
    docker logs --since "${since}" --tail "${tail_lines}" "${TEST_CONTAINER}" 2>&1
  fi
}

remove_test_worktrees() {
  while IFS= read -r worktree_path; do
    case "${worktree_path}" in
      "${TEST_WORKTREE_PREFIX}"-*)
        info "Removing worktree ${worktree_path}"
        git -C "${APP_DIR}" worktree remove --force "${worktree_path}" >/dev/null 2>&1 || true
        rm -rf -- "${worktree_path}"
        ;;
    esac
  done < <(git -C "${APP_DIR}" worktree list --porcelain | sed -n 's/^worktree //p')

  find /tmp -maxdepth 1 -type d -name 'kayo-test-*' -exec rm -rf -- {} +
}

remove_test_patches() {
  local patch
  for patch in /tmp/kayo-test-*.patch /tmp/kayo-welcome-mention.patch; do
    [ -e "${patch}" ] || continue
    case "${patch}" in
      /tmp/kayo-test-*.patch|/tmp/kayo-welcome-mention.patch)
        info "Removing patch ${patch}"
        rm -f -- "${patch}"
        ;;
    esac
  done
}

cmd_cleanup() {
  local drop_db=0

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --drop-test-db)
        drop_db=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown cleanup option: $1"
        ;;
    esac
  done

  require_app_dir
  require_command docker
  require_command git

  local prod_db
  local test_db
  prod_db="$(prod_db_name)"
  test_db="$(test_db_name)"
  guard_test_db_name "${prod_db}" "${test_db}"

  if container_exists "${TEST_CONTAINER}"; then
    info "Removing container ${TEST_CONTAINER}"
    docker rm -f "${TEST_CONTAINER}" >/dev/null
  fi

  info "Removing images ${TEST_IMAGE_REPO}:*"
  docker images --format '{{.Repository}}:{{.Tag}}' "${TEST_IMAGE_REPO}" \
    | while IFS= read -r image; do
        case "${image}" in
          "${TEST_IMAGE_REPO}:"*) docker rmi "${image}" >/dev/null 2>&1 || true ;;
        esac
      done

  remove_test_worktrees
  remove_test_patches

  if [ "${drop_db}" = "1" ]; then
    drop_test_db "${prod_db}" "${test_db}"
  fi

  echo "Cleanup complete."
}

main() {
  local command="${1:-}"
  if [ -z "${command}" ]; then
    usage
    exit 1
  fi
  shift

  case "${command}" in
    start) cmd_start "$@" ;;
    status) cmd_status "$@" ;;
    logs) cmd_logs "$@" ;;
    cleanup) cmd_cleanup "$@" ;;
    -h|--help|help) usage ;;
    *) die "unknown command: ${command}" ;;
  esac
}

main "$@"
