"""
loader.py — loads the legal terminology knowledge base from a JSONL file.

Each line in the JSONL file is one KB entry following the schema in
legal-template/schema.json.  Invalid / blank lines are skipped with a warning.
"""

import json
from pathlib import Path


def load_kb(kb_path: Path) -> list[dict]:
    """
    Load the knowledge base from a JSONL file.

    Args:
        kb_path: path to the .jsonl file

    Returns:
        List of dicts, one per valid entry. Empty list if the file is missing.
    """
    if not kb_path.exists():
        print(f"[KB] Warning: knowledge base not found at {kb_path}. "
              "Proceeding without terminology context.")
        return []

    entries = []
    with kb_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[KB] Warning: skipping malformed line {line_no}: {exc}")

    print(f"[KB] Loaded {len(entries)} entries from {kb_path}")
    return entries
