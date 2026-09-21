#!/usr/bin/env bash
# Docker entrypoint for the combined "backend" image: runs app, translation,
# field-mapping, ocr, and gateway as five separate uvicorn processes in one
# container. Mirrors scripts/start-backend.sh (the bare-metal equivalent) —
# none of the five services' own code is touched here, this just launches
# their existing entrypoints on their existing internal ports.
set -euo pipefail

RELOAD_FLAG=()
if [ "${AUTORELOAD:-1}" = "1" ]; then
  RELOAD_FLAG=(--reload)
fi

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT INT TERM

(cd /app && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "${RELOAD_FLAG[@]}") &
pids+=("$!")

(cd /app/document_processing/translation && exec uvicorn api_server:app --host 0.0.0.0 --port 8001 "${RELOAD_FLAG[@]}") &
pids+=("$!")

(cd /app/field_mapping_poc && exec uvicorn api:app --host 0.0.0.0 --port 8002 "${RELOAD_FLAG[@]}") &
pids+=("$!")

(cd /app/document_processing/ocr && exec uvicorn api:app --host 0.0.0.0 --port 8010 "${RELOAD_FLAG[@]}") &
pids+=("$!")

(cd /app/gateway && exec uvicorn main:app --host 0.0.0.0 --port 8080 "${RELOAD_FLAG[@]}") &
pids+=("$!")

# If any one process dies, bring the whole container down (rather than
# running silently degraded) so docker-compose's restart policy kicks in.
wait -n
exit $?
