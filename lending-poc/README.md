# Lending POC

Lending POC — FastAPI backend + PostgreSQL, plus a document
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

This builds and starts every service: `db`, `ollama`, `surya-inference`,
`backend` (which runs `app`, `field_mapping`, `translation`, `ocr`, and
`gateway` as five processes in one container — see
[Inside the backend container](#inside-the-backend-container) below), and
`frontend`.

The first run takes a while — Ollama and Surya both download models on
first use, and `backend`'s image build is the slowest of the bunch (it
installs every service's dependencies, including two separate CPU-only
PyTorch installs). Watch progress with:

```bash
docker compose logs -f
```

## 3. Run database migrations

`app` (one of the five processes in the `backend` container) doesn't run
migrations automatically on startup:

```bash
docker compose exec backend alembic -c db/alembic.ini upgrade head
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

Only two ports are published to the host:

| Service | URL | Notes |
|---|---|---|
| Frontend | http://localhost:5173 | Main UI |
| Gateway | http://localhost:8080 | Single public entrypoint — fronts app/OCR/translation/field-mapping. `GET /health` aggregates all four. |

Everything else — `app` (8000), `translation` (8001), `field_mapping` (8002),
`ocr` (8010), Postgres (5432), Redis (6379), Ollama (11434) and Surya inference (8000) — is
reachable only on the Docker network or on the `backend` container's own
loopback, not from the host. The gateway proxies every route the four backend
services define, so the frontend and any external caller has a complete path
through `:8080`.

To reach a service directly while debugging, go through the container rather
than re-publishing the port:

```bash
docker compose exec backend curl http://127.0.0.1:8010/health   # ocr
docker compose exec backend curl http://127.0.0.1:8001/health   # translation
docker compose exec db psql -U postgres lending_poc
```

If you want the ports back on the host for a local session, add a
`docker-compose.override.yml` (Compose merges it automatically, and `ports:`
entries are additive). Keep it out of the deployed environment — a published
port binds `0.0.0.0`, and Docker's iptables rules sit in front of the host
firewall, so these unauthenticated services would be internet-reachable.
Note that YAML anchors don't cross files, so an override needs its own
`backend-gpu:` block if you use the GPU profile.

`app`, `ocr`, `translation`, `field_mapping`, and `gateway` all run inside the
single `backend` container (see below).

### Inside the backend container

`backend` (and its GPU twin `backend-gpu`) runs eight independent
processes rather than one — `scripts/start-combined.sh` starts five APIs,
each with its own `uvicorn` command on its own port, plus three Celery
workers.

The ports below are **container-internal** — where each process listens
inside the container. Only the gateway's `8080` is published to the host
(see `ports:` in `docker-compose.yml`); the rest are reachable only from
inside the container, e.g. via `docker compose exec backend curl ...`.

| Process | Internal port | Role |
|---|---|---|
| `app` | 8000 | Case submission and decisioning (`/cases`) |
| `translation` | 8001 | OCR-text translation (queues `/translate/text` jobs) |
| `field_mapping` | 8002 | Maps OCR text onto a target JSON schema (queues `/map` jobs) |
| `ocr` | 8010 | Document text extraction (queues `/extract` jobs) |
| `gateway` | 8080 | Reverse-proxies to the other four on one public port; serves `GET /tasks/{task_id}` |
| `ocr@…` worker | — | Runs OCR jobs (calls `surya-inference`) |
| `translation@…` worker | — | Runs translation jobs (calls Ollama) |
| `field_mapping@…` worker | — | Runs field-mapping jobs (calls Ollama) |

None of the services' own code is aware they share a container — each is
the same FastAPI app or worker it would be if it ran alone, just co-located
for fewer containers to manage. `docker compose logs -f backend` shows all
processes' output interleaved.

### Background jobs (OCR, translation, field mapping)

These three steps can take minutes, so their APIs don't do the work inside
the HTTP request. `POST /extract`, `POST /translate/text` and `POST /map`
validate the input, queue a job in Redis and reply straight away with
`202 {"task_id": ...}`. A Celery worker (one per service, one job at a
time) runs the job and stores its result in Redis. Clients poll the
gateway until it's done:

```bash
curl -F "file=@document_processing/ocr/extraction_input/test-image.jpg" http://localhost:8080/extract
# → {"task_id": "f69eda69-...", "status": "PENDING"}

curl http://localhost:8080/tasks/f69eda69-...
# → {"status": "PENDING"}   waiting in the queue
# → {"status": "STARTED"}   a worker is on it
# → {"status": "SUCCESS", "result": {...}}  or  {"status": "FAILURE", "error": "..."}
```

The result is the same JSON each endpoint used to return directly. Celery
workers don't auto-reload: after changing a worker's code (`tasks.py`, the
extractor, the translator or mapper), run `docker compose restart backend`.

## Using a GPU

`surya-inference`, `backend` (which includes `ocr`), and `ollama` each
come in a CPU and a GPU variant, selected by `COMPOSE_PROFILES` in `.env`:

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
switching the profile is enough for it. `surya-inference` is built from a
CUDA base image for the `gpu` profile (see
[document_processing/ocr/README.md](document_processing/ocr/README.md)
for details); `backend-gpu` instead passes a `GPU=1` build arg that skips
pinning the CPU-only PyTorch wheel, so `ocr` (surya-ocr) installs
CUDA-enabled PyTorch instead. Note nothing in the backend image runs torch
inference any more, so this buys nothing today — see
[docker-compose.yml](docker-compose.yml) and the [Dockerfile](Dockerfile).

## Stopping and cleanup

```bash
docker compose down
```

Add `-v` to also delete the named volumes (`pgdata`, `ollama_models`,
`surya_models`, `hf_cache`) — this wipes the database and downloaded
models, so only do this if you want a clean slate:

```bash
docker compose down -v
```