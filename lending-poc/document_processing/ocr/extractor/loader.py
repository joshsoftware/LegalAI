"""Loading utilities: turn document files (PDF, PNG, JPEG) into a list of page images.

Supports both PDF files (multi-page) and image files (single page).
Each document type is handled appropriately to produce a consistent
list of PIL Images for OCR processing.
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

# Supported document formats
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def load_pages(document_path: str | Path, scale: float = DEFAULT_RENDER_SCALE) -> List[Image.Image]:
    """Load a document (PDF or image) as a list of PIL Images.

    Args:
        document_path: path to a document file (PDF, PNG, JPEG).
        scale: pdfium render scale for PDFs (2.0 ~= 144 DPI). Ignored for images.

    Returns:
        List of PIL Images, one per page. PDFs return multiple pages,
        images return a single-item list.
    """
    document_path = Path(document_path)
    extension = document_path.suffix.lower()
    
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {extension}. Supported: {supported}")

    if extension == ".pdf":
        return _load_pdf_pages(document_path, scale)
    else:
        return _load_image_file(document_path)


def _load_pdf_pages(pdf_path: Path, scale: float) -> List[Image.Image]:
    """Render every page of a PDF to a PIL Image."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        images = [page.render(scale=scale).to_pil() for page in pdf]
    finally:
        pdf.close()  # always release pdfium's native handles

    return images


def _load_image_file(image_path: Path) -> List[Image.Image]:
    """Load a single image file as a single-page document."""
    try:
        image = Image.open(image_path)
        # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
        if image.mode != "RGB":
            image = image.convert("RGB")
        return [image]
    except Exception as e:
        raise ValueError(f"Could not load image file {image_path}: {e}") from e


def find_documents(input_path: str | Path) -> List[Path]:
    """Resolve a CLI input path into a list of document files to process.

    - If `input_path` is a single supported file, returns just that file.
    - If `input_path` is a directory, recursively finds every supported document
      under it (including nested subfolders).
    
    Supported formats: PDF, PNG, JPEG
    """
    input_path = Path(input_path)

    if input_path.is_file():
        extension = input_path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise ValueError(f"Unsupported file type: {extension}. Supported: {supported}")
        return [input_path]

    if input_path.is_dir():
        documents = []
        for ext in SUPPORTED_EXTENSIONS:
            # Handle both .jpg and .jpeg patterns
            if ext == ".jpg":
                documents.extend(input_path.rglob("*.jpg"))
                documents.extend(input_path.rglob("*.JPG"))
            elif ext == ".jpeg":
                documents.extend(input_path.rglob("*.jpeg"))
                documents.extend(input_path.rglob("*.JPEG"))
            else:
                pattern = f"*{ext}"
                documents.extend(input_path.rglob(pattern))
                documents.extend(input_path.rglob(pattern.upper()))
        
        return sorted(set(documents))  # Remove duplicates and sort

    raise FileNotFoundError(f"Input path does not exist: {input_path}")


# Backward compatibility alias
find_pdfs = find_documents
