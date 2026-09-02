#!/bin/sh
# Downloads the same GGUF files Surya's own llamacpp backend fetches when it
# spawns its own server (surya/inference/backends/llamacpp.py:
# SURYA_GGUF_REPO / SURYA_GGUF_MODEL_FILE / SURYA_GGUF_MMPROJ_FILE), then
# starts llama-server with the equivalent flags so ocr-api can attach to it
# via SURYA_INFERENCE_URL instead of spawning its own.
set -e

MODEL_PATH="${MODEL_DIR}/${SURYA_GGUF_MODEL_FILE}"
MMPROJ_PATH="${MODEL_DIR}/${SURYA_GGUF_MMPROJ_FILE}"

if [ ! -f "$MODEL_PATH" ]; then
  echo "Downloading ${SURYA_GGUF_MODEL_FILE} from ${SURYA_GGUF_REPO}..."
  curl -fL -o "$MODEL_PATH" "https://huggingface.co/${SURYA_GGUF_REPO}/resolve/main/${SURYA_GGUF_MODEL_FILE}"
fi

if [ ! -f "$MMPROJ_PATH" ]; then
  echo "Downloading ${SURYA_GGUF_MMPROJ_FILE} from ${SURYA_GGUF_REPO}..."
  curl -fL -o "$MMPROJ_PATH" "https://huggingface.co/${SURYA_GGUF_REPO}/resolve/main/${SURYA_GGUF_MMPROJ_FILE}"
fi

# nvidia-smi only shows up here if the container was actually started with
# GPU access (via the "gpu" compose profile + NVIDIA Container Toolkit) -
# so this doubles as the CPU/GPU decision regardless of how the image was
# built, and fails safe to CPU if GPU access was requested but isn't there.
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  echo "GPU detected - offloading layers to GPU"
  NGL="${SURYA_INFERENCE_NGL:-999}"
else
  echo "No GPU detected - running on CPU"
  NGL=0
fi

exec llama-server \
  -m "$MODEL_PATH" \
  --mmproj "$MMPROJ_PATH" \
  -ngl "$NGL" \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --parallel "${SURYA_INFERENCE_PARALLEL:-4}" \
  --ctx-size "${SURYA_INFERENCE_CTX_SIZE:-49152}" \
  --alias "$SURYA_MODEL_ALIAS" \
  --jinja
