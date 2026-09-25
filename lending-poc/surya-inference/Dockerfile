# Builds llama.cpp's `llama-server` from source and serves it standalone, so
# ocr-api can point SURYA_INFERENCE_URL here instead of spawning its own copy
# in-process (see surya/inference/backends/llamacpp.py in the ocr-api image
# for the equivalent in-process spawn logic this mirrors).
#
# CPU by default. For a CUDA-capable build (paired with the "gpu" compose
# profile), pass:
#   --build-arg BASE_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04
#   --build-arg RUNTIME_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04
#   --build-arg GGML_CUDA=ON
# entrypoint.sh still probes for a visible GPU at container start and falls
# back to -ngl 0 (CPU) if none is found, so this image works either way.
ARG BASE_IMAGE=python:3.12-slim
ARG RUNTIME_IMAGE=python:3.12-slim

FROM ${BASE_IMAGE} AS build

ARG GGML_CUDA=OFF

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp /llama.cpp
WORKDIR /llama.cpp
RUN cmake -B build -DGGML_NATIVE=OFF -DGGML_CUDA=${GGML_CUDA} -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j"$(nproc)" --target llama-server

FROM ${RUNTIME_IMAGE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# llama-server is dynamically linked against the other .so files built
# alongside it (libllama-server-impl.so, libllama-common.so, libmtmd.so, ...),
# so the whole bin/ directory needs to come along, not just the executable.
COPY --from=build /llama.cpp/build/bin /opt/llama.cpp/bin
ENV LD_LIBRARY_PATH=/opt/llama.cpp/bin
RUN ln -s /opt/llama.cpp/bin/llama-server /usr/local/bin/llama-server

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
