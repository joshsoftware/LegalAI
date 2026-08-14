"""
retriever.py — matches KB entries against source text and formats the
terminology block that gets injected into the translation prompt.

Current strategy: fast substring pre-pass on the Devanagari `marathi` field.
To upgrade to embedding-based retrieval, replace or extend `retrieve()` —
the rest of the service is unaffected.
"""

_TERMINOLOGY_HEADER = (
    "\nRelevant legal terminology for this document "
    "(use the \"semantic\" rendering, NOT the \"literal\" one, "
    "unless the note says otherwise):\n"
)


def retrieve(text: str, kb: list[dict]) -> list[dict]:
    """
    Return KB entries whose `marathi` term appears verbatim in the source text.

    Args:
        text: raw OCR source text
        kb:   list of KB entry dicts (loaded by kb/loader.py)

    Returns:
        Subset of kb entries that matched.
    """
    matches = []
    for entry in kb:
        term = entry.get("marathi", "")
        if term and term in text:
            matches.append(entry)
    return matches


def format_terminology_block(entries: list[dict]) -> str:
    """
    Render matched KB entries into a formatted string for prompt injection.

    Each line follows the pattern:
        - <marathi> (<transliteration>): semantic = "…" | literal = "…" | note: …

    Args:
        entries: matched KB entries from retrieve()

    Returns:
        Formatted multi-line string, or empty string if no entries matched.
    """
    if not entries:
        return ""

    lines = [_TERMINOLOGY_HEADER]
    for entry in entries:
        marathi    = entry.get("marathi", "")
        translit   = entry.get("transliteration", "")
        semantic   = entry.get("semantic_english", "")
        literal    = entry.get("literal_gloss", "")
        note       = entry.get("common_mistranslation", "")

        line = f"- {marathi} ({translit}): semantic = \"{semantic}\""
        if literal:
            line += f" | literal = \"{literal}\""
        if note:
            line += f" | note: {note}"
        lines.append(line)

    return "\n".join(lines) + "\n"
