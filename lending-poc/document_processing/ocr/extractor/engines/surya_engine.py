"""Surya OCR engine implementation.

Thin adapter around Surya OCR's inference manager + recognition predictor.
All Surya-specific knowledge (its API shape, its raw `PageOCRResult`/`block`
attributes) is contained entirely in this file - translated into the
engine-agnostic `models.Block` / `models.PageResult` before leaving `run()`.
If Surya's API changes again (as it did between v1 and v2), only this file
needs to change.
"""

from __future__ import annotations

import os
from typing import List, Optional

from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor

from ..models import Block, PageResult
from .base import BaseOCREngine


class SuryaEngine(BaseOCREngine):
    """Lazily spins up the Surya inference backend and reuses it across calls.

    Instantiate this once (e.g. via `Extractor`) and reuse it for every PDF
    in a batch run, so the underlying vllm/llama.cpp server is only spawned
    once instead of once per document.
    """

    def __init__(self) -> None:
        self._manager = None
        self._recognizer = None

    def _ensure_ready(self) -> None:
        # Guard on the recognizer: it is what run() needs, and a failed start()
        # would otherwise leave a manager behind that skips this block forever.
        if self._recognizer is not None:
            return

        manager = SuryaInferenceManager()
        try:
            # Surya creates its inference manager lazily.  Starting it here
            # means an API startup check can fail fast when WSL is missing its
            # backend (llama-server on CPU, or vLLM/Docker on CUDA), instead
            # of making the first uploaded document appear to hang.
            manager.start()
            recognizer = RecognitionPredictor(manager)
        except Exception:
            # Don't leave a half-started backend running. A failure to clean up
            # must not replace the error that actually caused the problem.
            try:
                manager.stop()
            except Exception:
                pass
            raise

        # Assign only once every step succeeded, so a failure leaves the engine
        # untouched and the next call retries from scratch.
        self._manager = manager
        self._recognizer = recognizer

    def warm_up(self) -> None:
        """Start and validate Surya's inference backend without processing a file."""
        self._ensure_ready()

    @property
    def health_url(self) -> Optional[str]:
        """Health endpoint of an externally hosted Surya, or None if there isn't one.

        Surya treats an unset SURYA_INFERENCE_URL as "spawn my own backend
        in-process", so there is no endpoint to poll in that case.
        """
        external_url = os.getenv("SURYA_INFERENCE_URL")
        if not external_url:
            return None
        # Same /v1 -> /health mapping Surya applies to this variable internally.
        return external_url.rstrip("/").removesuffix("/v1") + "/health"

    def run(self, images: List[Image.Image]) -> List[PageResult]:
        self._ensure_ready()
        raw_predictions = self._recognizer(images)
        return [self._to_page_result(page) for page in raw_predictions]

    @staticmethod
    def _to_page_result(raw_page) -> PageResult:
        """Translate a Surya `PageOCRResult` into our generic `PageResult`."""
        blocks = [
            Block(
                label=block.label,
                html=block.html,
                bbox=list(block.bbox),
                confidence=block.confidence,
                reading_order=block.reading_order,
                skipped=block.skipped,
            )
            for block in raw_page.blocks
        ]
        return PageResult(blocks=blocks)
