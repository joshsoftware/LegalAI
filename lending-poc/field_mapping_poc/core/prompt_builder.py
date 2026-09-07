"""
Builds the system + user prompt sent to the model.

The schema is intentionally NOT a strict Pydantic model — callers pass
an arbitrary JSON object describing the fields they expect (a "target
shape"), and the model returns a same-shaped JSON with values filled
in, `null` where nothing was found, and permission to append genuinely
new fields it discovers.
"""
from __future__ import annotations

import json
from typing import Any, Dict

SYSTEM_PROMPT = """You are a precise information-extraction engine used in a \
document processing pipeline. You will be given:
1. A JSON "target schema" describing the fields expected in this document type. \
Each key is a field name; each value is a short type/description hint \
(e.g. "string", "number", "date (YYYY-MM-DD)"), not the actual value.
2. Raw OCR-extracted text of a document (may contain OCR noise, spacing \
errors, or be a translation of a non-English original).

Your job:
- Fill in the target schema with values found in the text.
- If a field's value cannot be confidently found in the text, set it to null. \
Never guess or fabricate a value.
- Preserve the exact key names and nesting structure of the target schema.
- Normalize every value you extract into a machine-readable form:
  - Dates: ISO 8601 `YYYY-MM-DD`. If the document only gives a month and \
year, output `YYYY-MM`.
  - Amounts: a bare JSON number with no currency symbol, no thousands \
separators and no spaces (4500.00, not "$ 4,500.00"). Where the schema has a \
separate currency field, put the currency there.
- Do not invent precision the document does not contain: if it says \
"March 2026", output "2026-03", never "2026-03-01".
- If OCR damage makes a value ambiguous, set the field to null rather than \
guessing at it.
- If you notice other clearly-named, clearly-valued fields in the text \
that are NOT part of the target schema but would be genuinely useful \
for this document type (e.g. a UAN number on a salary slip), ADD them \
to your JSON output at the same nesting level where they logically belong. \
Only add fields you are confident about — do not pad the output with guesses.
- Return ONLY a single valid JSON object. No commentary, no markdown fences, \
no explanation text before or after the JSON.
"""

USER_PROMPT_TEMPLATE = """TARGET SCHEMA:
{schema}

DOCUMENT TEXT:
\"\"\"
{document_text}
\"\"\"

Return the filled JSON now."""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_prompt(schema: Dict[str, Any], document_text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(
        schema=json.dumps(schema, indent=2, ensure_ascii=False),
        document_text=document_text.strip(),
    )
