"""
run.py — CLI entrypoint for batch translation.

Reads all .txt files from INPUT_DIR, translates each one via TranslationService,
and writes the results to OUTPUT_DIR. Filenames are preserved.

Usage (defaults from config.py):
    python run.py

Usage (override at runtime):
    python run.py --domain banking
    python run.py --domain legal --input /path/to/ocr/output --output ./results
    python run.py --model llama3.3:latest --no-health-check
"""

import argparse
import sys
from pathlib import Path

from translation_service import TranslationService
from translation_service import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-translate OCR .txt files from Indic languages to English."
    )
    parser.add_argument(
        "--domain", "-d",
        type=str,
        default=config.DEFAULT_DOMAIN,
        choices=config.SUPPORTED_DOMAINS,
        help=f"Translation domain — knowledge base to use (default: {config.DEFAULT_DOMAIN})",
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=config.INPUT_DIR,
        help=f"Directory of .txt files to translate (default: {config.INPUT_DIR})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=config.OUTPUT_DIR,
        help=f"Directory to write translated files to (default: {config.OUTPUT_DIR})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.MODEL_NAME,
        help=f"Model name to use (default: {config.MODEL_NAME})",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        default=config.MODEL_ADAPTER,
        help=f"Model adapter/backend (default: {config.MODEL_ADAPTER})",
    )
    parser.add_argument(
        "--no-health-check",
        action="store_true",
        help="Skip model health check before processing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir: Path  = args.input
    output_dir: Path = args.output

    # Validate input directory
    if not input_dir.exists():
        print(f"[run] Error: input directory does not exist: {input_dir}")
        sys.exit(1)

    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        print(f"[run] No .txt files found in {input_dir}. Nothing to do.")
        sys.exit(0)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialise service
    print(f"[run] Domain: {args.domain}")
    service = TranslationService(
        domain=args.domain,
        adapter_name=args.adapter,
        model_name=args.model,
        model_options=config.MODEL_OPTIONS,
    )

    # Optional health check
    if not args.no_health_check:
        print("[run] Running model health check…")
        if not service.health_check():
            print("[run] Error: model health check failed. "
                  "Is Ollama running and the model pulled?")
            sys.exit(1)
        print("[run] Health check passed.")

    # Batch translate
    total   = len(txt_files)
    success = 0
    failed  = 0

    print(f"[run] Processing {total} file(s) from {input_dir}\n")

    for idx, txt_file in enumerate(txt_files, start=1):
        print(f"[{idx}/{total}] {txt_file.name}")
        try:
            source_text = txt_file.read_text(encoding="utf-8")
            translation = service.translate(source_text)
            out_path    = output_dir / txt_file.name
            out_path.write_text(translation, encoding="utf-8")
            print(f"       ✓  written to {out_path}")
            success += 1
        except Exception as exc:
            print(f"       ✗  failed: {exc}")
            failed += 1

    print(f"\n[run] Done — {success} succeeded, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
