"""Surya OCR engine implementation.

Thin adapter around Surya OCR's inference manager + recognition predictor.
All Surya-specific knowledge (its API shape, its raw `PageOCRResult`/`block`
attributes) is contained entirely in this file - translated into the
engine-agnostic `models.Block` / `models.PageResult` before leaving `run()`.
If Surya's API changes again (as it did between v1 and v2), only this file
needs to change.
"""

from __future__ import annotations

from typing import List

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
        if self._manager is None:
            self._manager = SuryaInferenceManager()  # auto-spawns vllm or llama-server
            self._recognizer = RecognitionPredictor(self._manager)

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
