#!/usr/bin/env python3
"""Celery worker for OCR text extraction.

api.py no longer runs OCR inside the HTTP request. It saves the upload to
disk, queues an `ocr.extract` task in Redis and replies immediately with a
task id; a worker process started from this module picks the task up, runs
the same Extractor pipeline, and stores the result back in Redis, where the
gateway's GET /tasks/{task_id} reads it.

Usage (from this directory):
    celery -A tasks worker -Q ocr --concurrency=1 -n ocr@%h

--concurrency=1 replaces the asyncio.Lock api.py used to hold: one worker
process runs one task at a time, and later tasks wait in Redis.
"""

import json
import os
import threading
import time
from typing import Any, Dict

import redis
from celery import Celery
from celery.signals import worker_process_init

from extractor import Extractor, DEFAULT_ENGINE

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")


OCR_TASK_TIME_LIMIT_SECONDS = int(os.environ.get("OCR_TASK_TIME_LIMIT_SECONDS", "600"))

celery_app = Celery("ocr", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_default_queue="ocr",
    # Without this a task goes straight from PENDING to SUCCESS, so the UI
    # couldn't tell "waiting in the queue" apart from "being processed".
    task_track_started=True,
    # By default a worker reserves a few extra tasks ahead of time. With
    # tasks that take minutes, those reserved tasks would sit blocked behind
    # this worker even if another worker were free to take them.
    worker_prefetch_multiplier=1,
)

# Heartbeat api.py's /health reads to report on OCR readiness, since the API
# process no longer owns the Surya engine itself. The worker rewrites it
# every HEARTBEAT_INTERVAL_SECONDS; if it stops (worker stopped or crashed),
# the key expires and /health reports "unreachable".
WORKER_STATUS_KEY = "ocr:worker_status"
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = 30

# Cheap to construct: the Surya engine starts lazily (see _warm_up below), so
# importing this module from api.py never spins up any inference.
extractor = Extractor(engine=DEFAULT_ENGINE)

# The Surya engine crashes (segfault) if used from more than one thread at
# once. Warm-up runs on a background thread, so a task arriving mid-warm-up
# must wait for it rather than touch the half-started engine.
_engine_lock = threading.Lock()

_status: Dict[str, Any] = {"status": "initializing", "error": None}


def _heartbeat_loop() -> None:
    client = redis.Redis.from_url(RESULT_BACKEND)
    while True:
        try:
            client.set(WORKER_STATUS_KEY, json.dumps(_status), ex=HEARTBEAT_TTL_SECONDS)
        except redis.RedisError:
            pass  # Transient Redis outage; the next beat retries.
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


def _warm_up() -> None:
    try:
        with _engine_lock:
            extractor.engine.warm_up()
    except Exception as exc:
        # Kept visible through /health (and api.py refuses new uploads)
        # rather than crashing the worker, matching the old API behaviour.
        _status.update(status="unhealthy", error=str(exc))
    else:
        _status.update(status="healthy", error=None)


@worker_process_init.connect
def _start_background_threads(**_kwargs: Any) -> None:
    # Runs in each worker child process as it starts. Celery kills a child
    # that doesn't report "up" within a few seconds, and warming up Surya can
    # take minutes, so both jobs run on daemon threads instead of here.
    threading.Thread(target=_heartbeat_loop, name="ocr-heartbeat", daemon=True).start()
    threading.Thread(target=_warm_up, name="ocr-warm-up", daemon=True).start()


# time_limit is a hard limit: if the task is still running this many seconds
# after the worker started it, Celery kills the worker process (nothing in
# the task gets to run, not even the `finally` below) and starts a fresh one,
# which warms up again. A soft limit isn't used: a blocked Surya call can't
# be interrupted, so it never got the chance to act. Killing the worker
# doesn't cancel pages already sent to surya-inference: it finishes them
# anyway, so the next few jobs run slower until it catches up.
@celery_app.task(name="ocr.extract", time_limit=OCR_TASK_TIME_LIMIT_SECONDS)
def extract_task(file_path: str, filename: str, file_extension: str) -> Dict[str, Any]:
    """Run OCR on a file api.py saved to disk, then delete the file.

    Takes a path rather than the file's bytes so the task message in Redis
    stays small (uploads can be up to 50MB). Returns the same JSON shape
    /extract used to return directly.
    """
    try:
        with _engine_lock:
            result = extractor.process_document(file_path)
    finally:
        try:
            os.unlink(file_path)
        except OSError:
            pass  # Ignore cleanup errors

    return {
        "filename": filename,
        "file_type": file_extension,
        "pages_processed": len(result.json_data.get("pages", [])),
        "extraction": {
            "text": result.text,
            "html": result.html,
        },
        "metadata": {
            "processing_engine": DEFAULT_ENGINE,
        },
    }
