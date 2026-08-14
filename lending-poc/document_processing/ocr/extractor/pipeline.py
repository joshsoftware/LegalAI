"""High-level orchestration: find documents -> load -> OCR -> format -> save.

Public API:
    from extractor import Extractor

    extractor = Extractor(engine="surya")              # or engine=<BaseOCREngine instance>
    result  = extractor.process_document("file.pdf")   # single document, in-memory, no disk writes
    results = extractor.run(input_path="folder/")      # full folder pipeline, writes outputs to disk

Supports PDF, PNG, and JPEG files. `Extractor` is intentionally the *only* public surface 
of this package - whether you're running the CLI (`main.py`) or importing this as a library
into another service, you go through this one class. It depends only on
the abstract `BaseOCREngine` interface (see `engines/base.py`) and the
engine-agnostic `models.PageResult`/`models.Block` data (see `models.py`),
so swapping the OCR backend never requires touching this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from . import formatter
from .engines import BaseOCREngine, get_engine
from .loader import find_documents, load_pages

DEFAULT_INPUT_DIR = "extraction_input"
DEFAULT_OUTPUT_DIR = "extraction_output"
DEFAULT_ENGINE = "surya"


@dataclass
class ExtractionResult:
    document: str          # base filename, no extension
    source_path: Path
    text: str
    json_data: dict
    html: str


class Extractor:
    """Runs the full document -> OCR -> formatted-output pipeline.

    Supports PDF files (multi-page) and image files (PNG, JPEG - single page).
    
    Args:
        engine: either a registered engine name (e.g. "surya"), or an
            already-constructed `BaseOCREngine` instance (useful for
            injecting a custom or mocked engine). Defaults to "surya".
            The resolved engine is instantiated once and reused across
            every document processed by this `Extractor` instance, so any
            backend server it spawns (e.g. vllm/llama.cpp) only starts once.
    """

    def __init__(self, engine: Union[str, BaseOCREngine] = DEFAULT_ENGINE) -> None:
        self.engine: BaseOCREngine = get_engine(engine)

    def process_document(self, document_path: Union[str, Path]) -> ExtractionResult:
        """Run the full extraction pipeline on a single document and return the
        result. Supports PDF, PNG, and JPEG files. Does not write any files - 
        use `run()` for that, or save the returned result's fields yourself.
        """
        document_path = Path(document_path)

        images = load_pages(document_path)
        pages = self.engine.run(images)

        document_name = document_path.stem
        return ExtractionResult(
            document=document_name,
            source_path=document_path,
            text=formatter.build_text(pages),
            json_data=formatter.build_json(document_name, pages),
            html=formatter.build_html(document_name, pages),
        )

    def run(
        self,
        input_path: Union[str, Path] = DEFAULT_INPUT_DIR,
        output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
    ) -> List[ExtractionResult]:
        """Find every supported document under `input_path`, OCR it, and write outputs to
        `output_dir/{html,text,json}/`.

        Supports: PDF, PNG, JPEG files.

        Returns the list of `ExtractionResult` objects (also useful if you
        want to use the results in-process without re-reading the files
        back).
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        html_dir = output_dir / "html"
        text_dir = output_dir / "text"
        json_dir = output_dir / "json"
        for d in (html_dir, text_dir, json_dir):
            d.mkdir(parents=True, exist_ok=True)

        documents = find_documents(input_path)
        if not documents:
            print(f"No supported documents found under: {input_path}")
            print("Supported formats: PDF, PNG, JPEG")
            return []

        root = input_path if input_path.is_dir() else input_path.parent

        results = []
        for document_path in documents:
            print(f"Processing: {document_path}")
            result = self.process_document(document_path)
            out_name = self._output_name(document_path, root)

            (text_dir / f"{out_name}.txt").write_text(result.text, encoding="utf-8")
            (html_dir / f"{out_name}.html").write_text(result.html, encoding="utf-8")
            (json_dir / f"{out_name}.json").write_text(
                json.dumps(result.json_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print(f"  -> {text_dir / f'{out_name}.txt'}")
            print(f"  -> {html_dir / f'{out_name}.html'}")
            print(f"  -> {json_dir / f'{out_name}.json'}")

            results.append(result)

        return results

    @staticmethod
    def _output_name(document_path: Path, root: Path) -> str:
        """Derive a unique output base-name for a document, disambiguating
        collisions across nested folders by including the relative path.
        """
        try:
            rel = document_path.relative_to(root).with_suffix("")
            return rel.as_posix().replace("/", "__")
        except ValueError:
            # document_path wasn't under root (e.g. a single file was passed directly)
            return document_path.stem
