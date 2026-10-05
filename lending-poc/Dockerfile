FROM python:3.12-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app


ARG GPU=0
RUN if [ "$GPU" = "0" ]; then \
      pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi


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


FROM python:3.12-slim

WORKDIR /app

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

RUN chmod +x scripts/start-combined.sh

EXPOSE 8000 8001 8002 8010 8080

CMD ["bash", "scripts/start-combined.sh"]
