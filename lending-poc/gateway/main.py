#!/usr/bin/env python3
"""Single public FastAPI entrypoint that fronts the four independent
backend services (OCR, translation, field-mapping, and the core app/cases
API).

Each backend module keeps running exactly as it already does today, in its
own process/venv, on its own internal port. This gateway does not import or
alter any of their code — it only reverse-proxies HTTP requests to them, so
from the outside (the frontend, Postman, curl) there is a single server to
talk to on one port.

Internal service locations are configurable via env vars so the startup
script can point this at wherever it launched each service.
"""

import os
from contextlib import asynccontextmanager

import httpx
from celery import Celery
from celery.exceptions import TimeLimitExceeded
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

OCR_BASE_URL = os.environ.get("OCR_BASE_URL", "http://127.0.0.1:8010")
TRANSLATION_BASE_URL = os.environ.get("TRANSLATION_BASE_URL", "http://127.0.0.1:8001")
FIELD_MAPPING_BASE_URL = os.environ.get("FIELD_MAPPING_BASE_URL", "http://127.0.0.1:8002")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000")

# Where Celery workers store task state/results (see GET /tasks/{task_id}).
# The gateway only ever reads from it — it never sends or runs tasks — so it
# needs no broker and none of the services' task code.
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
celery_results = Celery("gateway", backend=CELERY_RESULT_BACKEND)

# Per-service request timeouts: how long one proxied HTTP call may take.
# /extract, /translate/text and /map only validate and queue work for a
# Celery worker, so they reply quickly (OCR's budget covers a 50MB upload).
# /translate/files and /cases still do their work inside the request —
# /cases also loads a sentence-transformers model on its first call — so
# translation and app keep longer budgets. How long the work itself may run
# is limited by the workers, not here.
OCR_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("OCR_REQUEST_TIMEOUT_SECONDS", "120"))
TRANSLATION_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("TRANSLATION_REQUEST_TIMEOUT_SECONDS", "300"))
FIELD_MAPPING_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("FIELD_MAPPING_REQUEST_TIMEOUT_SECONDS", "30"))
APP_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("APP_REQUEST_TIMEOUT_SECONDS", "300"))

# Headers that must not be forwarded as-is between hops (RFC 7230) plus a few
# that httpx/Starlette will recompute themselves and that would otherwise
# desync from the body we're actually sending/returning.
HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
}
REQUEST_STRIP_HEADERS = HOP_BY_HOP_HEADERS
RESPONSE_STRIP_HEADERS = HOP_BY_HOP_HEADERS | {"content-length", "content-encoding"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Client-level default only — every proxied route passes its own
    # *_REQUEST_TIMEOUT_SECONDS value, which overrides this.
    app.state.http = httpx.AsyncClient(timeout=120.0)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Lending POC Gateway", lifespan=lifespan)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _proxy(request: Request, base_url: str, path: str, timeout: float) -> Response:
    client: httpx.AsyncClient = request.app.state.http
    headers = {k: v for k, v in request.headers.items() if k.lower() not in REQUEST_STRIP_HEADERS}
    body = await request.body()
    try:
        upstream = await client.request(
            request.method,
            f"{base_url}{path}",
            headers=headers,
            params=list(request.query_params.multi_items()),
            content=body,
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Upstream service unavailable ({base_url}{path}): {exc}"},
        )

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in RESPONSE_STRIP_HEADERS
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)


# --- Business endpoints (unprefixed — these paths don't collide across the
# four modules, so the frontend needs no path changes beyond one base URL) ---

@app.post("/extract")
async def extract(request: Request) -> Response:
    return await _proxy(request, OCR_BASE_URL, "/extract", timeout=OCR_REQUEST_TIMEOUT_SECONDS)


@app.post("/translate/text")
async def translate_text(request: Request) -> Response:
    return await _proxy(request, TRANSLATION_BASE_URL, "/translate/text", timeout=TRANSLATION_REQUEST_TIMEOUT_SECONDS)


@app.post("/translate/files")
async def translate_files(request: Request) -> Response:
    return await _proxy(request, TRANSLATION_BASE_URL, "/translate/files", timeout=TRANSLATION_REQUEST_TIMEOUT_SECONDS)


@app.post("/map")
async def map_fields(request: Request) -> Response:
    return await _proxy(request, FIELD_MAPPING_BASE_URL, "/map", timeout=FIELD_MAPPING_REQUEST_TIMEOUT_SECONDS)


@app.post("/cases")
async def create_case(request: Request) -> Response:
    return await _proxy(request, APP_BASE_URL, "/cases", timeout=APP_REQUEST_TIMEOUT_SECONDS)


# --- Background task status (shared by every service that queues Celery
# tasks, e.g. POST /extract) ---

def _read_task(task_id: str) -> dict:
    result = celery_results.AsyncResult(task_id)
    body: dict = {"task_id": task_id, "status": result.state}
    if result.state == "SUCCESS":
        body["result"] = result.result
    elif result.state == "FAILURE":
        # On failure, .result holds the exception the task raised.
        if isinstance(result.result, TimeLimitExceeded):
            # Worker killed the job at its hard time limit; str() would only
            # give "TimeLimitExceeded(630,)".
            body["error"] = "The job took too long and was stopped."
        else:
            body["error"] = str(result.result)
    return body


@app.get("/tasks/{task_id}")
async def task_status(task_id: str) -> Response:
    try:
        # AsyncResult reads Redis synchronously, so keep it off the event loop.
        return JSONResponse(content=await run_in_threadpool(_read_task, task_id))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Task result store unavailable: {exc}"},
        )


# --- Per-service health (namespaced since all four modules define /health) ---
# Liveness probes, not business calls — kept short regardless of the
# per-service request timeouts above, matching the aggregate /health below.
HEALTH_PROXY_TIMEOUT_SECONDS = float(os.environ.get("HEALTH_PROXY_TIMEOUT_SECONDS", "5"))

_HEALTHY_UPSTREAM_STATUSES = frozenset({"healthy", "ok"})
_KNOWN_UNHEALTHY_UPSTREAM_STATUSES = frozenset(
    {"unhealthy", "unreachable", "initializing", "degraded"}
)


def _status_from_upstream(resp: httpx.Response) -> str:
    if resp.status_code >= 500:
        try:
            body_status = resp.json().get("status")
        except ValueError:
            body_status = None
        if isinstance(body_status, str) and body_status:
            if body_status in _HEALTHY_UPSTREAM_STATUSES:
                return f"unhealthy ({resp.status_code})"
            return body_status
        return f"unhealthy ({resp.status_code})"

    if resp.status_code >= 400:
        return f"unhealthy ({resp.status_code})"

    try:
        body_status = resp.json().get("status")
    except ValueError:
        body_status = None

    if not isinstance(body_status, str) or not body_status:
        return "unhealthy"

    if body_status in _HEALTHY_UPSTREAM_STATUSES:
        return "healthy"
    if body_status in _KNOWN_UNHEALTHY_UPSTREAM_STATUSES:
        return body_status
    return body_status


async def _probe_service(client: httpx.AsyncClient, base_url: str) -> str:
    try:
        resp = await client.get(f"{base_url}/health", timeout=HEALTH_PROXY_TIMEOUT_SECONDS)
    except httpx.RequestError:
        return "unreachable"
    return _status_from_upstream(resp)


@app.get("/ocr/health")
async def ocr_health(request: Request) -> Response:
    return await _proxy(request, OCR_BASE_URL, "/health", timeout=HEALTH_PROXY_TIMEOUT_SECONDS)


@app.get("/translation/health")
async def translation_health(request: Request) -> Response:
    return await _proxy(request, TRANSLATION_BASE_URL, "/health", timeout=HEALTH_PROXY_TIMEOUT_SECONDS)


@app.get("/field-mapping/health")
async def field_mapping_health(request: Request) -> Response:
    return await _proxy(request, FIELD_MAPPING_BASE_URL, "/health", timeout=HEALTH_PROXY_TIMEOUT_SECONDS)


@app.get("/app/health")
async def app_health(request: Request) -> Response:
    return await _proxy(request, APP_BASE_URL, "/health", timeout=HEALTH_PROXY_TIMEOUT_SECONDS)


@app.get("/health")
async def health(request: Request) -> dict:
    client: httpx.AsyncClient = request.app.state.http
    statuses: dict[str, str] = {}
    for name, base in (
        ("ocr", OCR_BASE_URL),
        ("translation", TRANSLATION_BASE_URL),
        ("field_mapping", FIELD_MAPPING_BASE_URL),
        ("app", APP_BASE_URL),
    ):
        statuses[name] = await _probe_service(client, base)

    overall = "healthy" if all(v == "healthy" for v in statuses.values()) else "degraded"
    return {"status": overall, "services": statuses}


@app.get("/")
async def root() -> dict:
    return {
        "message": "Lending POC Gateway",
        "endpoints": {
            "POST /extract": "Queue OCR text extraction; returns a task_id (proxies document_processing/ocr)",
            "GET /tasks/{task_id}": "Status and result of a queued background task",
            "POST /translate/text": "Queue text translation; returns a task_id (proxies document_processing/translation)",
            "POST /translate/files": "Translate files (proxies document_processing/translation)",
            "POST /map": "Queue field mapping; returns a task_id (proxies field_mapping_poc)",
            "POST /cases": "Case submission and decisioning (proxies app)",
            "GET /health": "Aggregated health of all four backend services",
            "GET /ocr/health": "OCR service health",
            "GET /translation/health": "Translation service health",
            "GET /field-mapping/health": "Field mapping service health",
            "GET /app/health": "App (cases) service health",
        },
    }
