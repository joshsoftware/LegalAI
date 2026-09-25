#!/usr/bin/env python3
"""FastAPI web service for Field Mapping.

Provides REST API endpoints for mapping OCR text to a target JSON schema.
Built as a wrapper around the existing FieldMapper.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8002 --reload

Endpoints:
    POST /map     - Map OCR text to the provided JSON schema
    GET /health   - Health check endpoint
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import uvicorn

from core.mapper import FieldMapper
from core.ollama_client import OllamaClientError
from core.response_parser import ResponseParseError

# Initialize field mapper (reused across requests for efficiency)
mapper = FieldMapper()


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

# The local Ollama model serves one generation at a time anyway; serialize
# calls through the shared client rather than letting them race across
# threads.
_map_lock = asyncio.Lock()

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
UNAVAILABLE_RETRY_AFTER_SECONDS = 30


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

@app.post("/map")
async def map_fields(request: MapRequest) -> Dict[str, Any]:
    """
    Map fields from OCR text based on the provided JSON format.
    
    Accepts:
    - ocr_text: String containing the raw OCR text.
    - json_format: String containing the target JSON schema.
    
    Returns: JSON response strictly adhering to the outer layer of json_format.
    """
    try:
        # Parse the JSON format string into a dictionary
        schema = json.loads(request.json_format)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format provided: {str(e)}"
        )

    # Fail fast when Ollama is known-down, before queueing on _map_lock —
    # otherwise concurrent callers pile up serially behind a doomed request.
    #
    # Deliberately `== "unreachable"`, NOT `!= "ok"`: "initializing" means the
    # server is up but the model hasn't answered yet — i.e. a cold load is in
    # progress — and those requests DO succeed if allowed to wait (~3min).
    # Rejecting them would turn working-but-slow into a hard failure.
    #
    # This is a fast path, not a guarantee: status can be up to
    # OLLAMA_HEALTH_RECHECK_SECONDS stale, and Ollama can wedge mid-call, so
    # the timeout/retry handling below still has to stand on its own.
    if mapper.client.health_status() == "unreachable":
        raise HTTPException(
            status_code=503,
            detail=STATUS_DETAIL["unreachable"],
            headers={"Retry-After": str(UNAVAILABLE_RETRY_AFTER_SECONDS)},
        )

    try:
        # Runs in a worker thread so this synchronous LLM call doesn't block
        # the event loop, serialized since the local model only serves one
        # generation at a time anyway.
        async with _map_lock:
            result = await run_in_threadpool(mapper.map_fields, schema, request.ocr_text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (OllamaClientError, ResponseParseError) as e:
        logger.error("Field mapping failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Field mapping error: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during field mapping: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": "Field Mapping API",
        "version": "1.0.0",
        "endpoints": {
            "POST /map": "Map OCR text to the provided JSON schema",
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
