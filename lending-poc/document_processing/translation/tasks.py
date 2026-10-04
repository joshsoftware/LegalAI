"""
tasks.py — Celery worker for text translation.

POST /translate/text validates the request and queues a `translation.translate`
task; a worker started from this module runs the LLM call and stores the
result in Redis, where the gateway's GET /tasks/{task_id} reads it.

Running (from this directory)
-------
    celery -A tasks worker -Q translation --concurrency=1 -n translation@%h

--concurrency=1 replaces the asyncio.Lock routes.py used to hold for this
endpoint: the local Ollama model serves one generation at a time anyway.
"""

import os
from typing import Any

from celery import Celery
from celery.signals import worker_process_init

from api.models import TextTranslateResponse, TranslationResult
from translation_service import TranslationService
from translation_service.config import SUPPORTED_DOMAINS, MODEL_NAME, MODEL_OPTIONS

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("translation", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_default_queue="translation",
    # Report STARTED so clients can tell "queued" apart from "processing".
    task_track_started=True,
    # Don't reserve extra tasks while a minutes-long one is running.
    worker_prefetch_multiplier=1,
)

# One TranslationService per domain, like api_server.py's app.state.services.
# Built in the worker only (see below): api.py imports this module too, and
# must not load every KB a second time.
_services: dict[str, TranslationService] = {}


@worker_process_init.connect
def _load_services(**_kwargs: Any) -> None:
    for domain in SUPPORTED_DOMAINS:
        _services[domain] = TranslationService(
            domain=domain,
            model_name=MODEL_NAME,
            model_options=MODEL_OPTIONS,
        )


@celery_app.task(name="translation.translate")
def translate_task(text: str, domain: str) -> dict[str, Any]:
    """Translate text using the given domain's KB. Text comes first so a
    previous task's output can be chained straight in. Returns the same
    JSON shape POST /translate/text used to return directly."""
    service = _services[domain]
    try:
        translation = service.translate(text)
    except Exception as exc:
        raise RuntimeError(f"Translation failed: {exc}") from exc

    # model_dump(): Celery stores results as JSON, not Pydantic objects.
    return TextTranslateResponse(
        result=TranslationResult(
            source="direct_text",
            domain=domain,
            translation=translation,
            kb_matches=service.kb_matches(text),
        )
    ).model_dump()
