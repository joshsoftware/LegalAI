#!/usr/bin/env python3
"""Celery worker for field mapping.

api.py validates a /map request and queues a `field_mapping.map` task; a
worker started from this module runs the LLM call and stores the result in
Redis, where the gateway's GET /tasks/{task_id} reads it.

Usage (from this directory):
    celery -A tasks worker -Q field_mapping --concurrency=1 -n field_mapping@%h

--concurrency=1 replaces the asyncio.Lock api.py used to hold: the local
Ollama model serves one generation at a time anyway.
"""

import os
from typing import Any, Dict

from celery import Celery

from core.mapper import FieldMapper

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("field_mapping", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_default_queue="field_mapping",
    # Report STARTED so clients can tell "queued" apart from "processing".
    task_track_started=True,
    # Don't reserve extra tasks while a minutes-long one is running.
    worker_prefetch_multiplier=1,
)

# Shared with api.py, which runs the Ollama health monitor on mapper.client.
mapper = FieldMapper()


# No Celery autoretry: OllamaClient.generate_json already retries transient
# failures and deliberately does NOT retry read timeouts.
@celery_app.task(name="field_mapping.map")
def map_task(ocr_text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Map document text onto the target schema. Text comes first so a
    previous task's output can be chained straight in."""
    return mapper.map_fields(schema, ocr_text)
