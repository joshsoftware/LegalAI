import json
from pathlib import Path
from ollama import chat

INPUT = Path("/Users/josh/Desktop/Josh/inovation_lab/surya_ocr_test/extraction_output/text")
OUTPUT = Path("./output/")
OUTPUT.mkdir(parents=True, exist_ok=True)

KB_PATH = Path("./legal-template/court_judgments_kb.jsonl")

PROMPT = """
Detect the source language and translate the following OCR document into clear English.

Rules:
- Translate the source text into English strictly based on the provided source text. Do not infer, add, omit, summarize, or rewrite any information unless it is explicitly present in the source. Preserve all words, fields, labels, numbers, names, dates, abbreviations, and document structure as accurately as possible. If a field is empty, keep it empty and do not map it to nearby or adjacent text. Translate legal terms, abbreviations, and domain-specific terminology using the approved legal glossary/dictionary only. If a term is unclear or not available in the glossary, preserve the original term and flag it for review instead of guessing its meaning.
- Return only the English translation.
- Preserve headings, paragraphs, dates, names, numbers, and lists.
- Correct OCR mistakes only when the intended wording is obvious.
- Do not summarize, omit, or add information.
{terminology_block}
Document:
{document}
"""

TERMINOLOGY_HEADER = (
    "\nRelevant legal terminology for this document "
    "(use the \"semantic\" rendering, NOT the \"literal\" one, unless the note says otherwise):\n"
)


def load_kb(kb_path: Path) -> list[dict]:
    """Load the legal translation knowledge base (JSONL, one entry per line)."""
    if not kb_path.exists():
        print(f"Warning: KB file not found at {kb_path}, proceeding without terminology context.")
        return []

    entries = []
    with kb_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def retrieve_relevant_entries(text: str, kb: list[dict]) -> list[dict]:
    """Fast substring pre-pass: keep KB entries whose Marathi term appears in the text."""
    matches = []
    for entry in kb:
        term = entry.get("marathi", "")
        if term and term in text:
            matches.append(entry)
    return matches


def format_terminology_block(entries: list[dict]) -> str:
    """Render matched KB entries into the prompt's terminology context block."""
    if not entries:
        return ""

    lines = [TERMINOLOGY_HEADER]
    for entry in entries:
        marathi = entry.get("marathi", "")
        translit = entry.get("transliteration", "")
        semantic = entry.get("semantic_english", "")
        literal = entry.get("literal_gloss", "")
        note = entry.get("common_mistranslation", "")

        line = f"- {marathi} ({translit}): semantic = \"{semantic}\""
        if literal:
            line += f" | literal = \"{literal}\""
        if note:
            line += f" | note: {note}"
        lines.append(line)

    return "\n".join(lines) + "\n"


kb = load_kb(KB_PATH)
print(f"Loaded {len(kb)} legal terminology entries from {KB_PATH}")

for txt_file in INPUT.glob("*.txt"):
    print(f"Processing {txt_file.name}")

    text = txt_file.read_text(encoding="utf-8")

    relevant_entries = retrieve_relevant_entries(text, kb)
    terminology_block = format_terminology_block(relevant_entries)
    print(f"  Matched {len(relevant_entries)} terminology entries")

    response = chat(
        model="gemma4:e4b",
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(document=text, terminology_block=terminology_block)
            }
        ],
        options={
            "num_predict": 16384,  # allow long documents to fully translate without truncation
            "num_ctx": 32768,      # ensure prompt + terminology + document all fit in context
        },
    )

    translation = response["message"]["content"]

    (OUTPUT / txt_file.name).write_text(translation, encoding="utf-8")

print("Done!")
