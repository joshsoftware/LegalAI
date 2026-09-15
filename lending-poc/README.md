# Lending POC

Lending POC — FastAPI backend + PostgreSQL (pgvector), plus a document
processing pipeline (OCR, translation, field mapping) fronted by a gateway,
and a React frontend. This guide covers running the **entire stack in
Docker**.

For running the `app` service natively against a containerized DB only
(e.g. for backend development with hot-reload outside Docker), see
[Database_setup.md](Database_setup.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
  (`docker compose version`)
- Git
- **Optional, for GPU acceleration**: an NVIDIA GPU, the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
  and (on Windows) WSL2 with GPU passthrough enabled

## 1. Clone and configure environment

```bash
git clone <repo-url>
cd lending-poc
cp .env.example .env
```

Generate a real `ENCRYPTION_KEY` — the app uses it to encrypt sensitive
database fields, and the placeholder value in `.env.example` is not a valid
key:

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

Paste the result into `ENCRYPTION_KEY=` in `.env`.

Leave `COMPOSE_PROFILES=cpu` as-is unless you have a working GPU setup —
see [Using a GPU](#using-a-gpu) below.

## 2. Start the stack

```bash
docker compose up --build -d
```

This builds and starts every service: `db`, `app`, `ollama`, `field_mapping`,
`translation`, `surya-inference` + `ocr`, `gateway`, and `frontend`.

The first run takes a while — Ollama and Surya both download models on
first use. Watch progress with:

```bash
docker compose logs -f
```

## 3. Run database migrations

The `app` container doesn't run migrations automatically on startup:

```bash
docker compose exec app alembic -c db/alembic.ini upgrade head
```

## 4. Pull the Ollama model

Needed by the `translation` and `field_mapping` services:

```bash
docker compose exec ollama ollama pull gemma4:e4b-it-qat
```

(Substitute whatever `OLLAMA_MODEL` is set to in `.env` if you changed it.
If you're running the GPU profile, use `ollama-gpu` instead of `ollama` in
the command above.)

## 5. Verify it's running

| Service | URL | Notes |
|---|---|---|
| Frontend | http://localhost:5173 | Main UI |
| Gateway | http://localhost:8080 | Fronts OCR / translation / field-mapping |
| App (backend API) | http://localhost:8000 | Docs at `/docs`; health at `/health` |
| Postgres | localhost:55439 | pgvector-enabled |
| OCR | http://localhost:8010 | Not normally called directly |
| Translation | http://localhost:8001 | Not normally called directly |
| Field mapping | http://localhost:8002 | Not normally called directly |
| Surya inference | http://localhost:8500 | OCR's inference backend |

There are effectively two subsystems sharing this compose file: the
`app` + `db` lending backend, and a separate OCR/translation/field-mapping
pipeline fronted by `gateway`. The frontend talks to the gateway for
document processing and to the app for everything else.

## Using a GPU

`surya-inference`/`ocr` and `ollama` each come in a CPU and a GPU variant,
selected by `COMPOSE_PROFILES` in `.env`:

- `COMPOSE_PROFILES=cpu` (default) — always works, no GPU required.
- `COMPOSE_PROFILES=gpu` — requires an NVIDIA GPU on the host plus the
  NVIDIA Container Toolkit (and, on Windows, WSL2 GPU passthrough).

To switch:

```bash
# in .env
COMPOSE_PROFILES=gpu
```

```bash
docker compose up --build -d
```

Both GPU containers detect GPU access at startup and fall back to CPU
automatically if it isn't actually usable — but `docker compose up` will
fail to create the containers at all if the toolkit isn't installed,
since the GPU device reservation can't be satisfied.

Ollama's own image auto-detects CUDA at runtime with no separate build, so
switching the profile is enough for it; `surya-inference`/`ocr` are built
from CUDA base images specifically for the `gpu` profile (see
[docker-compose.yml](docker-compose.yml) and
[document_processing/ocr/README.md](document_processing/ocr/README.md)
for details).

## Stopping and cleanup

```bash
docker compose down
```

Add `-v` to also delete the named volumes (`pgdata`, `ollama_models`,
`surya_models`) — this wipes the database and downloaded models, so only
do this if you want a clean slate:

```bash
docker compose down -v
```