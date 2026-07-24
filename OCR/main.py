#!/usr/bin/env python3
"""Command-line entry point for the OCR text-extraction pipeline.

Usage:
    python main.py                                # processes everything under extraction_input/
    python main.py path/to/file.pdf                # processes a single specific PDF
    python main.py path/to/folder                  # recursively processes all PDFs in a custom folder
    python main.py path/to/folder --engine surya    # explicitly select an OCR engine (default: surya)
"""

import argparse

from extractor import DEFAULT_ENGINE, DEFAULT_INPUT_DIR, Extractor
from extractor.engines import ENGINE_REGISTRY


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCR text extraction on PDFs.")
    parser.add_argument(
        "input_path",
        nargs="?",
        default=DEFAULT_INPUT_DIR,
        help=f"PDF file or folder to process (default: {DEFAULT_INPUT_DIR}/)",
    )
    parser.add_argument(
        "--engine",
        default=DEFAULT_ENGINE,
        choices=sorted(ENGINE_REGISTRY),
        help=f"OCR engine to use (default: {DEFAULT_ENGINE})",
    )

    args = parser.parse_args()

    extractor = Extractor(engine=args.engine)
    results = extractor.run(input_path=args.input_path)

    print(f"\nDone. Processed {len(results)} PDF(s).")


if __name__ == "__main__":
    main()
