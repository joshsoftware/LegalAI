ARG LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda

FROM ${LLAMA_IMAGE}

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ensure llama-server is in system PATH
RUN if [ -f /app/llama-server ]; then ln -sf /app/llama-server /usr/local/bin/llama-server; fi

ENV SURYA_GGUF_REPO=datalab-to/surya-ocr-2-gguf \
    SURYA_GGUF_MODEL_FILE=surya-2.gguf \
    SURYA_GGUF_MMPROJ_FILE=surya-2-mmproj.gguf \
    SURYA_MODEL_ALIAS=datalab-to/surya-ocr-2 \
    MODEL_DIR=/models \
    PORT=8000

RUN mkdir -p /models

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]