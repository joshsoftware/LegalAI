#!/usr/bin/env python3
"""FastAPI web service for OCR text extraction.

Accepts document uploads (PDF, PNG, JPEG) and queues them for OCR. The OCR
itself runs in a separate Celery worker (see tasks.py), so this service
replies straight away with a task id instead of holding the request open for
the minutes a document can take. Clients poll the gateway's
GET /tasks/{task_id} for the result.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8010 --reload
    celery -A tasks worker -Q ocr --concurrency=1 -n ocr@%h   (the worker)

Endpoints:
    POST /extract - Validate and queue a document; returns 202 + task_id
    GET /health   - Health check, reflecting the OCR worker's status
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool
import redis.asyncio as aioredis
from redis.exceptions import RedisError
import uvicorn

from extractor import DEFAULT_ENGINE
from extractor.loader import SUPPORTED_EXTENSIONS
from tasks import RESULT_BACKEND, WORKER_STATUS_KEY, extract_task

# Initialize FastAPI app
app = FastAPI(
    title="OCR Text Extraction API",
    description="Upload documents (PDF, PNG, JPEG) for OCR text extraction using Surya",
    version="1.0.0",
)

# File size limit
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_FILE_SIZE_MB", "50")) * 1024 * 1024


# Uploads reach the worker as a file path, so this directory must be visible
# to both processes. They share a container today; if the worker ever moves
# to its own container, this has to become a shared volume. Deliberately not
# under /app, which docker-compose bind-mounts from the host's repo checkout.
UPLOAD_DIR = Path(os.environ.get("OCR_UPLOAD_DIR", Path(tempfile.gettempdir()) / "ocr-uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Reads the heartbeat the worker writes to Redis (see tasks.py).
_redis = aioredis.Redis.from_url(RESULT_BACKEND)


async def _worker_status() -> Dict[str, Any]:
    """The OCR worker's last reported status ("initializing", "healthy" or
    "unhealthy"), or "unreachable" if its heartbeat has expired."""
    try:
        raw = await _redis.get(WORKER_STATUS_KEY)
    except RedisError as exc:
        return {"status": "unreachable", "error": f"Cannot reach Redis: {exc}"}
    if raw is None:
        return {"status": "unreachable", "error": "No OCR worker is running (no heartbeat received)."}
    return json.loads(raw)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check that distinguishes an online API from a ready OCR worker."""
    worker = await _worker_status()
    response: Dict[str, Any] = {
        "status": worker["status"],
        "service": "OCR Text Extraction API",
        "engine": DEFAULT_ENGINE,
        "ocr_ready": worker["status"] == "healthy",
    }
    if worker.get("error"):
        response["ocr_error"] = worker["error"]
    return response


@app.post("/extract", status_code=202)
async def extract_text(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Queue an uploaded document for OCR text extraction.

    Accepts: PDF, PNG, JPEG files
    Returns: 202 with a task_id; poll GET /tasks/{task_id} (on the gateway)
    for the extracted text, HTML representation, and metadata.
    """

    # Refuse uploads only when OCR can't run at all. "initializing" is fine:
    # the task just waits in the queue until the worker's warm-up finishes.
    worker = await _worker_status()
    if worker["status"] in ("unhealthy", "unreachable"):
        raise HTTPException(
            status_code=503,
            detail=f"OCR inference is unavailable: {worker.get('error')}",
        )

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_extension}. Supported: {supported}"
        )

    # Check file size
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # The worker deletes this file once it has processed it.
    with tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, suffix=file_extension, delete=False) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name

    try:
        # .delay() talks to Redis synchronously, so keep it off the event loop.
        task = await run_in_threadpool(extract_task.delay, temp_file_path, file.filename, file_extension)
    except Exception as e:
        # Nothing was queued, so no worker will ever clean this file up.
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=503,
            detail=f"Could not queue the document for OCR: {str(e)}"
        )

    return {"task_id": task.id, "status": "PENDING"}


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": "OCR Text Extraction API",
        "version": "1.0.0",
        "supported_formats": list(SUPPORTED_EXTENSIONS),
        "endpoints": {
            "POST /extract": "Queue a document for OCR; returns a task_id",
            "GET /health": "Health check",
            "GET /": "This information"
        },
        "usage": "Upload files to /extract using multipart/form-data, then poll GET /tasks/{task_id} on the gateway"
    }

if __name__ == "__main__":
    # This allows running the API directly: python api.py
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8010,
        reload=True
    )
