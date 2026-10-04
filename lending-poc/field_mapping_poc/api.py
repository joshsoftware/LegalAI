#!/usr/bin/env python3
"""FastAPI web service for Field Mapping.

Provides REST API endpoints for mapping OCR text to a target JSON schema.
The mapping itself (an LLM call) runs in a separate Celery worker (see
tasks.py); /map validates the request, queues it and replies with a task id.
Clients poll the gateway's GET /tasks/{task_id} for the result.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8002 --reload
    celery -A tasks worker -Q field_mapping --concurrency=1 -n field_mapping@%h

Endpoints:
    POST /map     - Validate and queue a mapping; returns 202 + task_id
    GET /health   - Health check endpoint
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import uvicorn

from tasks import map_task, mapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the background Ollama-reachability monitor backing /health."""
    await mapper.client.start_monitoring()
    yield
    await mapper.client.stop_monitoring()


# Initialize FastAPI app
app = FastAPI(
    title="Field Mapping API",
    description="Map OCR text to a target JSON schema using LLM.",
    version="1.0.0",
    lifespan=lifespan,
)

logger = logging.getLogger(__name__)

class MapRequest(BaseModel):
    ocr_text: str = Field(..., description="Raw OCR text to extract information from")
    json_format: str = Field(..., description="Target JSON schema as a string")


HealthStatus = Literal["ok", "initializing", "unreachable"]

STATUS_DETAIL = {
    "unreachable": "Ollama is unreachable.",
    "initializing": "Ollama reachable — waiting for the model to respond.",
    "ok": "Model is loaded and responding.",
}

# Retry-After hint sent with the 503 in /map when Ollama is unreachable.
# Deliberately not OLLAMA_HEALTH_RETRY_SECONDS (5s) — that's how fast our own
# monitor re-probes, but telling clients to retry that fast just hammers a
# service that is genuinely down.
UNAVAILABLE_RETRY_AFTER_SECONDS = int(os.environ.get("UNAVAILABLE_RETRY_AFTER_SECONDS", "30"))


class HealthResponse(BaseModel):
    status: HealthStatus = Field(
        description=(
            "'unreachable' if Ollama isn't responding, 'initializing' if it's "
            "reachable but the model hasn't responded yet (e.g. cold-loading), "
            "'ok' if the model is loaded and responding."
        )
    )
    detail: str = Field(description="Human-readable explanation of `status`.")
    service: str = Field(description="This service's name.")
    model: str = Field(description="Model name currently configured.")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint — reflects live Ollama reachability, not just process liveness."""
    status = mapper.client.health_status()
    return HealthResponse(
        status=status,
        detail=STATUS_DETAIL[status],
        service="Field Mapping API",
        model=mapper.client.model,
    )

@app.post("/map", status_code=202)
async def map_fields(request: MapRequest) -> Dict[str, Any]:
    """
    Queue a mapping of OCR text onto the provided JSON format.

    Accepts:
    - ocr_text: String containing the raw OCR text.
    - json_format: String containing the target JSON schema.

    Returns: 202 with a task_id; poll GET /tasks/{task_id} (on the gateway)
    for the JSON strictly adhering to the outer layer of json_format.
    """
    try:
        # Parse the JSON format string into a dictionary
        schema = json.loads(request.json_format)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format provided: {str(e)}"
        )

    # Same checks FieldMapper.map_fields makes, done here so bad input still
    # gets an immediate 400 instead of a queued task that fails later.
    if not request.ocr_text or not request.ocr_text.strip():
        raise HTTPException(status_code=400, detail="document_text is empty")
    if not schema:
        raise HTTPException(status_code=400, detail="schema must not be empty")

    # Fail fast when Ollama is known-down, before queueing the task —
    # otherwise tasks pile up in the queue behind a doomed one.
    #
    # Deliberately `== "unreachable"`, NOT `!= "ok"`: "initializing" means the
    # server is up but the model hasn't answered yet — i.e. a cold load is in
    # progress — and those requests DO succeed if allowed to wait (~3min).
    # Rejecting them would turn working-but-slow into a hard failure.
    #
    # This is a fast path, not a guarantee: status can be up to
    # OLLAMA_HEALTH_RECHECK_SECONDS stale, and Ollama can wedge mid-call, so
    # OllamaClient's own timeout/retry handling still has to stand on its own.
    if mapper.client.health_status() == "unreachable":
        raise HTTPException(
            status_code=503,
            detail=STATUS_DETAIL["unreachable"],
            headers={"Retry-After": str(UNAVAILABLE_RETRY_AFTER_SECONDS)},
        )

    try:
        # .delay() talks to Redis synchronously, so keep it off the event loop.
        task = await run_in_threadpool(map_task.delay, request.ocr_text, schema)
    except Exception as e:
        logger.error("Could not queue field mapping: %s", e)
        raise HTTPException(status_code=503, detail=f"Could not queue the mapping: {str(e)}")

    return {"task_id": task.id, "status": "PENDING"}

@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": "Field Mapping API",
        "version": "1.0.0",
        "endpoints": {
            "POST /map": "Queue a mapping of OCR text to the provided JSON schema; returns a task_id",
            "GET /health": "Health check",
            "GET /": "This information"
        }
    }

if __name__ == "__main__":
    # This allows running the API directly: python api.py
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )
