"""
api/routes.py — FastAPI router with all translation endpoints.

Endpoints
---------
GET  /health
    Checks model reachability and shows KB sizes per domain.

POST /translate/text
    Translates a single plain-text string. Accepts a `domain` field in the body.

POST /translate/files
    Accepts one or more uploaded .txt files. Accepts a `domain` query parameter.
    Files are processed sequentially; a failure on one does not abort the others.
"""

import asyncio

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Request, status
from fastapi.concurrency import run_in_threadpool

from .models import (
    TextTranslateRequest,
    TextTranslateResponse,
    FilesTranslateResponse,
    HealthResponse,
    TranslationResult,
    DomainLiteral,
)
from translation_service.config import SUPPORTED_DOMAINS, DEFAULT_DOMAIN, MODEL_NAME, MODEL_ADAPTER
from translation_service.kb.retriever import retrieve

router = APIRouter()

# service.translate() makes a blocking call to the local Ollama model, which
# (per this module's own README) only serves one request at a time. Run it
# in a worker thread so it doesn't freeze the event loop for other requests
# (e.g. /health), and serialize access via a lock to match that constraint.
_translate_lock = asyncio.Lock()


def _get_service(request: Request, domain: str):
    """Retrieve the pre-loaded TranslationService for the given domain from app state."""
    services: dict = request.app.state.services
    if domain not in services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domain '{domain}' not available. Supported: {SUPPORTED_DOMAINS}",
        )
    return services[domain]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

# Human-readable detail shown alongside HealthResponse.status.
STATUS_DETAIL = {
    "unreachable": "Ollama is unreachable.",
    "initializing": "Ollama reachable — waiting for the model to respond.",
    "ok": "Model is loaded and responding.",
}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Model health check",
    tags=["Utility"],
)
async def health(request: Request):
    """Returns model reachability and KB sizes for all loaded domains."""
    # Check health via the default domain service (one model shared across all).
    # health_status() is an instant, non-blocking read of state tracked by a
    # background monitor — it never calls Ollama itself (see ollama_adapter.py).
    default_service = request.app.state.services[DEFAULT_DOMAIN]
    status = default_service.health_status()

    kb_entries = {
        domain: svc.kb_size()
        for domain, svc in request.app.state.services.items()
    }

    return HealthResponse(
        status=status,
        detail=STATUS_DETAIL[status],
        model=MODEL_NAME,
        adapter=MODEL_ADAPTER,
        domains=SUPPORTED_DOMAINS,
        kb_entries=kb_entries,
    )


# ---------------------------------------------------------------------------
# Translate — direct text
# ---------------------------------------------------------------------------

@router.post(
    "/translate/text",
    response_model=TextTranslateResponse,
    summary="Translate a plain-text string",
    tags=["Translation"],
)
async def translate_text(body: TextTranslateRequest, request: Request):
    """
    Accepts a JSON body and returns the English translation.

    Set `domain` to `"banking"` (default) or `"legal"` to use the correct KB.

    Example:
    ```json
    {
      "text": "बँकेने कर्जाची रक्कम मंजूर केली.",
      "domain": "banking"
    }
    ```
    """
    service = _get_service(request, body.domain)
    try:
        matches = retrieve(body.text, service._kb)
        async with _translate_lock:
            translation = await run_in_threadpool(service.translate, body.text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Translation failed: {exc}",
        )

    return TextTranslateResponse(
        result=TranslationResult(
            source="direct_text",
            domain=body.domain,
            translation=translation,
            kb_matches=len(matches),
        )
    )


# ---------------------------------------------------------------------------
# Translate — uploaded files
# ---------------------------------------------------------------------------

@router.post(
    "/translate/files",
    response_model=FilesTranslateResponse,
    summary="Translate one or more uploaded .txt files",
    tags=["Translation"],
)
async def translate_files(
    request: Request,
    domain: DomainLiteral = Query(
        default=DEFAULT_DOMAIN,
        description=f"Translation domain to use. One of: {SUPPORTED_DOMAINS}.",
    ),
    files: list[UploadFile] = File(
        ..., description="One or more plain-text (.txt) files to translate."
    ),
):
    """
    Accepts one or more `.txt` file uploads and a `domain` query param.
    Returns a translation result for each file.
    Failures are returned inline — processing continues for remaining files.

    Example:
    ```
    POST /translate/files?domain=banking
    files: [bank_statement.txt, salary_slip.txt]
    ```
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file must be provided.",
        )

    service = _get_service(request, domain)
    results = []
    succeeded = 0
    failed = 0

    for upload in files:
        filename = upload.filename or "unknown"
        try:
            raw_bytes = await upload.read()
            text      = raw_bytes.decode("utf-8")
            matches   = retrieve(text, service._kb)
            async with _translate_lock:
                translation = await run_in_threadpool(service.translate, text)

            results.append(TranslationResult(
                source=filename,
                domain=domain,
                translation=translation,
                kb_matches=len(matches),
            ))
            succeeded += 1

        except UnicodeDecodeError:
            results.append(TranslationResult(
                source=filename,
                domain=domain,
                translation="[ERROR] File could not be decoded as UTF-8.",
                kb_matches=0,
            ))
            failed += 1

        except Exception as exc:
            results.append(TranslationResult(
                source=filename,
                domain=domain,
                translation=f"[ERROR] Translation failed: {exc}",
                kb_matches=0,
            ))
            failed += 1

    return FilesTranslateResponse(
        results=results,
        total=len(files),
        succeeded=succeeded,
        failed=failed,
    )
