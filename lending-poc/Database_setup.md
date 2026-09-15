# lending-poc

Lending POC backend — FastAPI + PostgreSQL (pgvector).

## Requirements

- Docker (for PostgreSQL via `pgvector/pgvector:pg16`) — or a local Postgres with the `pgvector` extension
- `pip`

## 1. Clone and set up a virtualenv

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## 2. Configure environment variables

Create a `.env` file in the project root:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55439/lending_poc
ENCRYPTION_KEY=<32-byte base64 key>
DEBUG=true
```

Generate an `ENCRYPTION_KEY`:

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

`DATABASE_URL` must point at the Postgres instance you'll run in step 3. If you run the app itself inside Docker (`docker compose up app`), it uses `DATABASE_URL_DOCKER` instead (defaults to the `db` service host) — see `docker-compose.yml`.

## 3. Start the database

```bash
docker compose up -d db
```

This starts Postgres with pgvector on host port `55439` (mapped from container port `5432`), and waits until it reports healthy.

## 4. Run database migrations

Alembic's config lives under `db/`, so point `-c` at it explicitly from the project root:

```bash
alembic -c db/alembic.ini upgrade head
```

Useful commands:

```bash
alembic -c db/alembic.ini current   # show current DB revision
alembic -c db/alembic.ini heads     # show latest migration on disk
alembic -c db/alembic.ini history   # full migration chain
```
