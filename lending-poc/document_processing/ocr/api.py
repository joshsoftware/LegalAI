#!/usr/bin/env python3
"""FastAPI web service for OCR text extraction.

Provides REST API endpoints for uploading and processing documents (PDF, PNG, JPEG).
Built as a thin wrapper around the existing Extractor pipeline.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8010 --reload

Endpoints:
    POST /extract - Upload and process a document
    GET /health   - Health check endpoint
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool
import uvicorn

from extractor import Extractor, DEFAULT_ENGINE
from extractor.loader import SUPPORTED_EXTENSIONS

# Initialize extractor (reused across requests for efficiency)
extractor = Extractor(engine=DEFAULT_ENGINE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Surya without making the HTTP service unavailable during warm-up."""
    app.state.ocr_ready = False
    app.state.ocr_error = None

    async def warm_up() -> None:
        try:
            await run_in_threadpool(extractor.engine.warm_up)
        except Exception as exc:
            # Keep the API available for diagnostics.  /extract will return a
            # useful 503 instead of holding an upload open while Surya retries
            # a missing/misconfigured WSL inference runtime.
            app.state.ocr_error = str(exc)
        else:
            app.state.ocr_ready = True

    warm_up_task = asyncio.create_task(warm_up())
    try:
        yield
    finally:
        warm_up_task.cancel()
        try:
            await warm_up_task
        except asyncio.CancelledError:
            pass


# Initialize FastAPI app
app = FastAPI(
    title="OCR Text Extraction API",
    description="Upload documents (PDF, PNG, JPEG) for OCR text extraction using Surya",
    version="1.0.0",
    lifespan=lifespan,
)

# File size limit (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# The Surya engine crashes (segfault) if invoked from more than one thread at
# once, so concurrent /extract calls must queue rather than run in parallel.
_extract_lock = asyncio.Lock()

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check that distinguishes an online API from ready OCR inference."""
    response: Dict[str, Any] = {
        "status": "healthy" if app.state.ocr_ready else "initializing",
        "service": "OCR Text Extraction API",
        "engine": DEFAULT_ENGINE,
        "ocr_ready": app.state.ocr_ready,
    }
    if app.state.ocr_error:
        response["status"] = "unhealthy"
        response["ocr_error"] = app.state.ocr_error
    return response

@app.post("/extract")
async def extract_text(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Extract text from an uploaded document.
    
    Accepts: PDF, PNG, JPEG files
    Returns: Extracted text, HTML representation, and metadata
    """
    
    # Never accept an upload when the OCR runtime is not available.  Without
    # this guard Surya can block the request for its full backend timeout.
    if not app.state.ocr_ready:
        detail = "OCR inference is still initializing"
        if app.state.ocr_error:
            detail = f"OCR inference is unavailable: {app.state.ocr_error}"
        raise HTTPException(status_code=503, detail=detail)

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
    
    # Reset file pointer for processing
    await file.seek(0)
    
    # Process the document
    temp_file = None
    temp_file_path = ""
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            suffix=file_extension, 
            delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Runs in a worker thread (so this blocking call doesn't freeze the
        # event loop for other requests) but serialized via a lock (so two
        # extractions never actually run at the same time, which segfaults).
        async with _extract_lock:
            result = await run_in_threadpool(extractor.process_document, temp_file_path)
        
        # Prepare response
        response_data = {
            "filename": file.filename,
            "file_type": file_extension,
            "pages_processed": len(result.json_data.get("pages", [])),
            "extraction": {
                "text": result.text,
                "html": result.html,
                # "structured_data": result.json_data
            },
            "metadata": {
                "processing_engine": DEFAULT_ENGINE
            }
        }
        
        return response_data
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing document: {str(e)}"
        )
    
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass  # Ignore cleanup errors

@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": "OCR Text Extraction API",
        "version": "1.0.0",
        "supported_formats": list(SUPPORTED_EXTENSIONS),
        "endpoints": {
            "POST /extract": "Upload and process a document",
            "GET /health": "Health check",
            "GET /": "This information"
        },
        "usage": "Upload files to /extract endpoint using multipart/form-data"
    }

if __name__ == "__main__":
    # This allows running the API directly: python api.py
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8010,
        reload=True
    )
