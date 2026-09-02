#!/usr/bin/env bash
# Starts Ollama + the three independent backend modules (OCR, translation,
# field-mapping), each in its own venv/process exactly as they already run
# today, then starts the gateway that fronts all of them on one public port.
#
# None of the three modules' own code is touched by this script — it only
# creates/reuses their venvs, installs their own requirements.txt, and
# launches their existing uvicorn entrypoints on internal ports.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="python3.12"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b-it-qat}"

GATEWAY_PORT=8000
OCR_PORT=8010
TRANSLATION_PORT=8001
FIELD_MAPPING_PORT=8002

pids=()
cleanup() {
  echo ""
  echo "Shutting down backend services..."
  for pid in "${pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait_healthy() {
  local name="$1" port="$2"
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      echo "  OK  ${name} ready on :${port}"
      return 0
    fi
    sleep 1
  done
  echo "  !!  ${name} did not report healthy on :${port} within 30s (continuing anyway)" >&2
}

echo "=== 1/5: Ollama server ==="
if pgrep -x "ollama" >/dev/null 2>&1; then
  echo "Ollama already running - skipping."
else
  echo "Starting Ollama server..."
  ollama serve >/tmp/lending-poc-ollama.log 2>&1 &
  pids+=("$!")
  sleep 2
fi

echo "Pulling model ${OLLAMA_MODEL} (no-op if already present)..."
if ! ollama pull "${OLLAMA_MODEL}"; then
  echo "WARNING: 'ollama pull ${OLLAMA_MODEL}' failed. Translation/field-mapping requests will error until a valid model is available (override with OLLAMA_MODEL=... make start-backend)." >&2
fi

echo ""
echo "=== 2/5: OCR service (internal :${OCR_PORT}) ==="
cd "$ROOT_DIR/document_processing/ocr"
[ -d surya-env ] || "$PYTHON_BIN" -m venv surya-env
surya-env/bin/pip install --upgrade pip --quiet
surya-env/bin/pip install -r requirements.txt --quiet
surya-env/bin/python -m uvicorn api:app --host 127.0.0.1 --port "$OCR_PORT" &
pids+=("$!")

echo ""
echo "=== 3/5: Translation service (internal :${TRANSLATION_PORT}) ==="
cd "$ROOT_DIR/document_processing/translation"
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
.venv/bin/python -m uvicorn api_server:app --host 127.0.0.1 --port "$TRANSLATION_PORT" &
pids+=("$!")

echo ""
echo "=== 4/5: Field mapping service (internal :${FIELD_MAPPING_PORT}) ==="
cd "$ROOT_DIR/field_mapping_poc"
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port "$FIELD_MAPPING_PORT" &
pids+=("$!")

echo ""
echo "Waiting for backend services to become healthy..."
wait_healthy "OCR" "$OCR_PORT"
wait_healthy "Translation" "$TRANSLATION_PORT"
wait_healthy "Field mapping" "$FIELD_MAPPING_PORT"

echo ""
echo "=== 5/5: Gateway (public :${GATEWAY_PORT}) ==="
cd "$ROOT_DIR/gateway"
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo ""
echo "=================================================="
echo " Gateway (single server, use this from the frontend):"
echo "   http://localhost:${GATEWAY_PORT}"
echo ""
echo " Internal services (not meant to be called directly):"
echo "   OCR           http://127.0.0.1:${OCR_PORT}"
echo "   Translation   http://127.0.0.1:${TRANSLATION_PORT}"
echo "   Field mapping http://127.0.0.1:${FIELD_MAPPING_PORT}"
echo "=================================================="
echo "Press Ctrl+C to stop all services."
echo ""

OCR_BASE_URL="http://127.0.0.1:${OCR_PORT}" \
TRANSLATION_BASE_URL="http://127.0.0.1:${TRANSLATION_PORT}" \
FIELD_MAPPING_BASE_URL="http://127.0.0.1:${FIELD_MAPPING_PORT}" \
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "$GATEWAY_PORT"
