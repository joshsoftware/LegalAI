"""Abstract base class every OCR engine must implement.

This is the single seam that makes OCR backends swappable. `pipeline.py`
and `formatter.py` only ever talk to this interface (and the `models.py`
data model it returns) - they never know or care whether the concrete
implementation is Surya, Tesseract, a vLLM-hosted vision model, a cloud OCR
API, etc.

To add a new engine:
    1. Create `extractor/engines/your_engine.py`.
    2. Subclass `BaseOCREngine` and implement `run()`, translating your
       engine's native output into `models.Block` / `models.PageResult`.
    3. Register it in `extractor/engines/__init__.py`'s `ENGINE_REGISTRY`.

Nothing else in the codebase needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from PIL import Image

from ..models import PageResult


class BaseOCREngine(ABC):
    """Contract for any OCR backend used by the extraction pipeline."""

    @abstractmethod
    def run(self, images: List[Image.Image]) -> List[PageResult]:
        """Run OCR on a list of page images for a single document.

        Args:
            images: one `PIL.Image` per page, in page order.

        Returns:
            One `PageResult` per input image, in the same order.
        """
        raise NotImplementedError
