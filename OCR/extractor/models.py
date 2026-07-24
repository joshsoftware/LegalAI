"""Engine-agnostic data model shared by every OCR engine and by `formatter.py`.

Any OCR engine (Surya, Tesseract, a vLLM-backed model, a cloud OCR API, ...)
must translate its own native output into these two dataclasses inside its
`run()` method. Nothing downstream (formatter, pipeline) ever imports or
touches an engine-specific type - this is the single contract that makes
engines swappable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Block:
    """A single recognized content block on a page (a paragraph, heading,
    table, list item, etc.)

    Attributes:
        label: canonical block type, e.g. "Text", "SectionHeader", "Table",
            "PageHeader", "Picture", "ListGroup".
        html: recognized content as HTML (tables as `<table>`, plain
            paragraphs as `<p>`, etc.)
        bbox: `[x0, y0, x1, y1]` position of the block on the rendered page.
        confidence: 0-1 engine confidence score for this block. Engines that
            don't provide one should default to `1.0`.
        reading_order: 0-indexed position of this block within the page, in
            reading order.
        skipped: True for blocks that were detected but not OCR'd (e.g. pure
            images/figures). Skipped blocks are excluded from text/JSON/HTML
            output by `formatter.py`.
    """

    label: str
    html: str
    bbox: List[float]
    confidence: float = 1.0
    reading_order: int = 0
    skipped: bool = False


@dataclass
class PageResult:
    """All recognized blocks for a single page, in reading order."""

    blocks: List[Block] = field(default_factory=list)
