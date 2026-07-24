"""Loading utilities: turn a PDF file into a list of page images.

Kept deliberately narrow (PDF-only for v1) but structured so that adding
support for plain image files (.png/.jpg/etc.) later is a small addition -
just another branch in `load_pages`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pypdfium2 as pdfium
from PIL import Image

# Render scale tuned for OCR accuracy on Indic/mixed-script documents.
# scale=2 ~= 144 DPI (pdfium's base unit is 72 DPI). Surya's own docs
# recommend keeping images under ~2048px width for the best
# accuracy/throughput tradeoff - scale=2 keeps typical A4 pages comfortably
# under that while still being sharp enough for OCR.
DEFAULT_RENDER_SCALE = 2.0


def load_pages(pdf_path: str | Path, scale: float = DEFAULT_RENDER_SCALE) -> List[Image.Image]:
    """Render every page of a PDF to a PIL Image.

    Args:
        pdf_path: path to a .pdf file.
        scale: pdfium render scale (2.0 ~= 144 DPI).

    Returns:
        List of PIL Images, one per page, in page order.
    """
    pdf_path = Path(pdf_path)
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Only PDF files are supported right now, got: {pdf_path}")

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        images = [page.render(scale=scale).to_pil() for page in pdf]
    finally:
        pdf.close()  # always release pdfium's native handles

    return images


def find_pdfs(input_path: str | Path) -> List[Path]:
    """Resolve a CLI input path into a list of PDF files to process.

    - If `input_path` is a single .pdf file, returns just that file.
    - If `input_path` is a directory, recursively finds every .pdf under it
      (including nested subfolders).
    """
    input_path = Path(input_path)

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {input_path}")
        return [input_path]

    if input_path.is_dir():
        return sorted(p for p in input_path.rglob("*.pdf"))

    raise FileNotFoundError(f"Input path does not exist: {input_path}")
