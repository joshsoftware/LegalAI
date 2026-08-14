"""OCR-powered document text-extraction package.

Public API:
    from extractor import Extractor

    extractor = Extractor(engine="surya")           # pick/plug in any registered engine
    result  = extractor.process_pdf("file.pdf")      # single PDF, in-memory
    results = extractor.run(input_path="folder/")    # full folder pipeline, writes to disk

`Extractor` is the sole public entry point of this package - see
`extractor/pipeline.py` for details, `extractor/engines/base.py` for the
OCR engine contract, and `extractor/models.py` for the engine-agnostic
result data model.
"""

from .pipeline import DEFAULT_ENGINE, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, Extractor, ExtractionResult

__all__ = [
    "Extractor",
    "ExtractionResult",
    "DEFAULT_ENGINE",
    "DEFAULT_INPUT_DIR",
    "DEFAULT_OUTPUT_DIR",
]
