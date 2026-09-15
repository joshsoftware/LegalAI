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
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import uvicorn

from core.mapper import FieldMapper
from core.ollama_client import OllamaClientError
from core.response_parser import ResponseParseError

# Initialize FastAPI app
app = FastAPI(
    title="Field Mapping API",
    description="Map OCR text to a target JSON schema using LLM.",
    version="1.0.0"
)

# Initialize field mapper (reused across requests for efficiency)
mapper = FieldMapper()

# The local Ollama model serves one generation at a time anyway; serialize
# calls through the shared client rather than letting them race across
# threads.
_map_lock = asyncio.Lock()

logger = logging.getLogger(__name__)

class MapRequest(BaseModel):
    ocr_text: str = Field(..., description="Raw OCR text to extract information from")
    json_format: str = Field(..., description="Target JSON schema as a string")

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint to verify API is running."""
    return {
        "status": "healthy",
        "service": "Field Mapping API"
    }

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
