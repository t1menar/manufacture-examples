#!/usr/bin/env bash
# Hello World end-to-end on docker compose (design doc §1.4, §10.3).
#
#   e2e/run.sh                 # infra mode while CORE_IMAGE is empty, full mode otherwise
#   CORE_IMAGE=ghcr.io/t1menar/manufacture-core:pr-12 e2e/run.sh
#   SDK_REF=<sha> e2e/run.sh   # module images on another SDK commit
#   E2E_KEEP=1 e2e/run.sh      # leave the stack running for inspection
#
# Infra mode: PostgreSQL, RabbitMQ 4, MinIO (+ bucket), local registry come up healthy and
#   are probed; the four module images are built and pushed to localhost:5001 and load their
#   module. The core part is reported as SKIPPED.
# Full mode: + core (`serve`, docker driver), then e2e/hello_world_e2e.py checks the run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Pins from versions.env; values already set in the environment win.
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  if [[ -z "${!key+x}" ]]; then export "$key=$value"; fi
done < versions.env

COMPOSE=(docker compose -f e2e/compose.yml)
TIMEOUT="${E2E_TIMEOUT:-180}"
log() { printf '[e2e] %s\n' "$*"; }

cleanup() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    log "failure: service status and recent logs"
    "${COMPOSE[@]}" --profile core ps -a || true
    "${COMPOSE[@]}" --profile core logs --no-color --tail 200 || true
    # Module containers are started by the core's docker driver, outside compose.
    for c in $(docker ps -aq --filter "label=manufacture.dev/module" 2>/dev/null); do
      docker logs --tail 100 "$c" 2>&1 | sed "s/^/[$c] /" || true
    done
  fi
  if [[ "${E2E_KEEP:-0}" != "1" ]]; then
    "${COMPOSE[@]}" --profile core down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  exit $rc
}
trap cleanup EXIT

log "infrastructure: postgres, rabbitmq, minio, registry"
"${COMPOSE[@]}" up -d --wait --wait-timeout "$TIMEOUT" postgres rabbitmq minio registry
"${COMPOSE[@]}" up --exit-code-from minio-init minio-init >/dev/null

log "probes"
"${COMPOSE[@]}" exec -T postgres psql -U mf -d mf -tAc 'select 1' | grep -qx 1
"${COMPOSE[@]}" exec -T rabbitmq rabbitmq-diagnostics -q check_running
"${COMPOSE[@]}" run --rm --no-deps --entrypoint /bin/sh minio-init -c \
  'mc alias set e2e http://minio:9000 mf-e2e mf-e2e-local-only >/dev/null && mc ls e2e/mf-blobs >/dev/null'
log "infrastructure is healthy (rabbitmq $("${COMPOSE[@]}" exec -T rabbitmq rabbitmqctl -q version))"

log "module images (SDK ${SDK_REF:0:12}) -> localhost:5001"
make -C hello-world images push manifests SDK_REF="$SDK_REF"

if [[ -z "${CORE_IMAGE:-}" ]]; then
  log "SKIPPED core part: CORE_IMAGE is empty in versions.env (no runnable core image yet;"
  log "  needs manufacture-core C4 engine, C5 registration, C6 docker driver + image)"
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "e2e: infrastructure and module images OK; **core part skipped** (CORE_IMAGE not set)" >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

log "core: $CORE_IMAGE"
MF_ADMIN_TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"  # never printed
export MF_ADMIN_TOKEN CORE_IMAGE
"${COMPOSE[@]}" --profile core up -d core
MF_URL="http://127.0.0.1:${E2E_CORE_PORT:-8080}" \
  python3 e2e/hello_world_e2e.py --timeout "$TIMEOUT" ${E2E_REQUIRE_METRICS:+--require-metrics}
