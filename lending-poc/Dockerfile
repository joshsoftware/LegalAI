FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU by default: pin the CPU-only torch wheel so the image doesn't pull
# CUDA deps it can't use (sentence-transformers, pulled in via pyproject.toml
# below, and surya-ocr, pulled in via document_processing/ocr/requirements.txt,
# both depend on torch). Paired with the "gpu" compose profile, build with
# --build-arg GPU=1 to skip the pin and let their default CUDA-enabled wheel
# install instead.
ARG GPU=0
RUN if [ "$GPU" = "0" ]; then \
      pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi

# app, field_mapping, translation, ocr, and gateway each keep their own
# dependency manifest, installed as-is — this image runs all five as
# separate uvicorn processes behind one entrypoint (scripts/start-combined.sh),
# it doesn't merge their code. Manifests are copied (and installed) before
# the rest of the source so this layer is only invalidated when a dependency
# changes, not on every code edit.
#
# The four requirements.txt files are staged in /deps rather than under their
# real paths on purpose: `pip install .` below relies on setuptools' flat-
# layout discovery in /app, which aborts if it finds sibling top-level package
# directories (field_mapping_poc/, document_processing/, gateway/) next to
# pyproject.toml. Keeping /app empty apart from pyproject.toml at install time
# preserves the behaviour this step had when it built app/ alone.
COPY pyproject.toml ./
COPY field_mapping_poc/requirements.txt /deps/field_mapping.txt
COPY document_processing/translation/requirements.txt /deps/translation.txt
COPY document_processing/ocr/requirements.txt /deps/ocr.txt
COPY gateway/requirements.txt /deps/gateway.txt

RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir -r /deps/field_mapping.txt \
    && pip install --no-cache-dir -r /deps/translation.txt \
    && pip install --no-cache-dir -r /deps/ocr.txt \
    && pip install --no-cache-dir -r /deps/gateway.txt

COPY . .

RUN chmod +x scripts/start-combined.sh

EXPOSE 8000 8001 8002 8010 8080

CMD ["scripts/start-combined.sh"]
