"""Converts engine-agnostic OCR output (`models.PageResult`/`models.Block`)
into three consumer-facing formats:

- plain text  (machines, simple case)
- JSON        (machines, structured case)
- HTML        (humans)

Operates purely against the generic data model in `models.py` - it has no
knowledge of which OCR engine produced the results, so swapping engines
never requires touching this file.

See README.md "Output formats" section for the full design rationale and
field-mapping explanation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .models import PageResult

_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """Strip HTML tags down to plain text.

    Good enough for OCR output, which is simple HTML (p/b/u/table/tr/td/br),
    not full documents - we just need readable text, not a full HTML parser.
    """
    # Turn common block/line-break tags into newlines/spaces before stripping,
    # so table cells and paragraphs don't get smashed together.
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|tr|div|li)>", "\n", text)
    text = re.sub(r"<(td|th)>", " ", text)
    text = _TAG_RE.sub("", text)
    # Collapse excess whitespace but keep paragraph breaks.
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def build_json(document_name: str, pages: List[PageResult]) -> Dict[str, Any]:
    """Build the structured JSON representation for one document.

    See README.md for the field mapping table (engine field -> our field).
    """
    page_entries = []
    for page_number, page_result in enumerate(pages, start=1):
        blocks = []
        for block in page_result.blocks:
            if block.skipped:
                continue
            blocks.append(
                {
                    "type": block.label,
                    "order": block.reading_order,
                    "text": html_to_text(block.html),
                    "html": block.html,
                    "confidence": block.confidence,
                    "bbox": list(block.bbox),
                }
            )
        page_entries.append({"page_number": page_number, "blocks": blocks})

    return {
        "document": document_name,
        "page_count": len(pages),
        "pages": page_entries,
    }


def build_text(pages: List[PageResult]) -> str:
    """Build the plain-text representation for one document.

    Concatenates every non-skipped block's text, in reading order, with
    clear page-break markers. No markup, no metadata.
    """
    page_texts = []
    for page_number, page_result in enumerate(pages, start=1):
        block_texts = [
            html_to_text(block.html)
            for block in page_result.blocks
            if not block.skipped
        ]
        page_body = "\n\n".join(block_texts)
        page_texts.append(f"--- Page {page_number} ---\n{page_body}")

    return "\n\n".join(page_texts)


_HTML_STYLE = """
body { font-family: sans-serif; padding: 20px; }
.page { border: 1px solid #ccc; margin-bottom: 30px; padding: 15px; border-radius: 8px; }
.page-title { background: #333; color: #fff; padding: 6px 12px; margin: -15px -15px 15px -15px;
border-radius: 8px 8px 0 0; font-weight: bold; }
.block { margin-bottom: 12px; }
table, td, th { border: 1px solid #999; border-collapse: collapse; padding: 4px; }
"""


def build_html(document_name: str, pages: List[PageResult]) -> str:
    """Build the styled, human-readable HTML report for one document."""
    parts = [
        "<html><head><meta charset='utf-8'>",
        f"<title>{document_name}</title>",
        "<style>",
        _HTML_STYLE,
        "</style></head><body>",
    ]

    for page_number, page_result in enumerate(pages, start=1):
        parts.append("<div class='page'>")
        parts.append(f"<div class='page-title'>Page {page_number}</div>")
        for block in page_result.blocks:
            if block.skipped:
                continue
            parts.append("<div class='block'>")
            parts.append(block.html)
            parts.append("</div>")
        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)
