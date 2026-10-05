#!/usr/bin/env bash
# Runs the Surya OCR model server directly on macOS so llama.cpp can use the
# Apple GPU (Metal). Docker on a Mac can't reach Metal, so the surya-inference
# container is CPU-only there. This mirrors surya-inference/entrypoint.sh;
# keep the two in sync if the flags or model files change there.
#
# Usage:   ./scripts/start_surya_native.sh
# Then run the rest of the stack WITHOUT the surya-inference container, with the
# backend's SURYA_INFERENCE_URL set to http://host.docker.internal:8000/v1
# (see docker-compose.yml).
#
# Every setting below can be overridden from the environment, e.g.
#   SURYA_INFERENCE_PARALLEL=1 SURYA_INFERENCE_CTX_SIZE=16384 ./scripts/start_surya_native.sh
set -euo pipefail

# Same model files the container downloads.
SURYA_GGUF_REPO="${SURYA_GGUF_REPO:-datalab-to/surya-ocr-2-gguf}"
SURYA_GGUF_MODEL_FILE="${SURYA_GGUF_MODEL_FILE:-surya-2.gguf}"
SURYA_GGUF_MMPROJ_FILE="${SURYA_GGUF_MMPROJ_FILE:-surya-2-mmproj.gguf}"
# The backend asks the server for the model by this exact name.
SURYA_MODEL_ALIAS="${SURYA_MODEL_ALIAS:-datalab-to/surya-ocr-2}"

MODEL_DIR="${MODEL_DIR:-$HOME/.cache/surya-gguf}"
# 127.0.0.1 keeps the server private to this Mac. Docker Desktop's
# host.docker.internal can still reach it. If the backend container gets
# "connection refused", rerun with HOST=0.0.0.0 (this also exposes the server
# to your local network).
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
# 999 = "put every layer on the GPU". Use 0 to force CPU.
NGL="${SURYA_INFERENCE_NGL:-999}"
PARALLEL="${SURYA_INFERENCE_PARALLEL:-4}"
CTX_SIZE="${SURYA_INFERENCE_CTX_SIZE:-49152}"

if ! command -v llama-server >/dev/null 2>&1; then
  echo "llama-server not found. Install it with: brew install llama.cpp" >&2
  exit 1
fi

# Fail early if something (e.g. a leftover surya-inference container) already
# owns the port, instead of a confusing llama-server bind error.
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop whatever is using it, or set PORT=<other>." >&2
  exit 1
fi

mkdir -p "$MODEL_DIR"

# Download each file only if it isn't already there. Download to a .part file
# first so an interrupted download isn't mistaken for a finished one next run.
download_if_missing() {
  local file="$1"
  local path="$MODEL_DIR/$file"
  if [ ! -f "$path" ]; then
    echo "Downloading $file from $SURYA_GGUF_REPO..."
    curl -fL -o "$path.part" "https://huggingface.co/$SURYA_GGUF_REPO/resolve/main/$file"
    mv "$path.part" "$path"
  fi
}

download_if_missing "$SURYA_GGUF_MODEL_FILE"
download_if_missing "$SURYA_GGUF_MMPROJ_FILE"

echo "Starting llama-server on http://$HOST:$PORT (GPU layers: $NGL)"

# exec replaces this script with llama-server, so Ctrl+C stops it directly.
exec llama-server \
  -m "$MODEL_DIR/$SURYA_GGUF_MODEL_FILE" \
  --mmproj "$MODEL_DIR/$SURYA_GGUF_MMPROJ_FILE" \
  -ngl "$NGL" \
  --host "$HOST" \
  --port "$PORT" \
  --parallel "$PARALLEL" \
  --ctx-size "$CTX_SIZE" \
  --alias "$SURYA_MODEL_ALIAS" \
  --jinja
