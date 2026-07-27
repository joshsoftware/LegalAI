"""
Extraction/validate_llm/llm_field_checks.py
Whole-case LLM semantic validation: one Ollama call per case, given ONLY
a numbered list of the fields worth a semantic check, asked to return the
INVALID ones as JSON.

The rule engine (field_rules.py) already handles anything checkable by
type/regex/range (IDs, dates, numeric ranges, etc.) before this ever
runs, so this step only has to judge free-text/semantic correctness:
does the *content* of a field actually match its *name* (e.g. a name
string sitting in an address field).

Design choices that specifically target failure modes observed with 4B
local models (Qwen, Gemma):
  1. SEMANTIC_FIELDS WHITELIST — only fields with real semantic risk are
     sent at all (case_number/dates/IDs etc. have no "wrong content"
     failure mode worth an LLM call). Smaller prompt, fewer chances for
     the model to invent a problem where none exists.
  2. NO FULL CASE JSON — earlier versions also embedded the entire
     rule-cleaned case JSON "for reference", doubling context for no
     benefit (the numbered list already has every value) and inviting
     cross-field comparisons the prompt explicitly forbids.
  3. INVALID-ONLY JSON OUTPUT — asking for `n=<i> verdict=valid` on every
     single field forces the model to produce dozens of repetitive lines
     it can lose count of. Asking only for the invalid ones, plus a
     `checked` count the caller verifies against the true field count,
     gets most of the robustness of "enumerate everything" at a fraction
     of the output size.
  4. CLOSED, SMALL REASON VOCABULARY — few, non-overlapping codes are
     easier for a small model to apply consistently than many similar
     ones.
  5. TOLERANT PARSING — the model is not perfectly reliable about exact
     key names/casing, so parsing normalizes minor variation instead of
     failing closed.

Every returned problem is independently re-verified against the original
input in check_case() before it is trusted (hallucination backstop) —
this verification is a correctness guarantee that holds regardless of
model or prompt wording.
"""
import json
import logging
import re

from Extraction.validate_llm.ollama_client import ask_json

logger = logging.getLogger('pipeline')

# Only these fields carry real semantic risk (free text where the wrong
# *kind* of content could land) — everything else (IDs, dates, numbers,
# amounts) is already covered by field_rules.py and isn't worth a
# model call.
SEMANTIC_FIELDS = {
    'name', 'role', 'address', 'office_address', 'designation',
    'district', 'state', 'purpose', 'nature_of_disposal',
}

# Closed vocabulary the model must pick from — no free-text reasons.
# Kept small and non-overlapping so a small model can apply it
# consistently (a name-shaped value in a name field and a role-label in
# a name field are both just "wrong_content", not two different things).
_REASON_CODES = {
    'wrong_content'      : 'Value is the wrong kind of information for this field',
    'missing_location'   : 'Address-like field has no building/street/locality/city/PIN at all',
    'missing_designation': 'Designation-like field has no judicial/professional title in it',
    'narrative_text'      : 'Value is a full sentence/narrative where a short label was expected',
}
_REASON_CODES_TEXT = "\n".join(f"  {code} — {desc}" for code, desc in _REASON_CODES.items())

def build_case_for_prompt(case_entities: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """
    case_entities: {'persons': [dict, ...], 'judges': [dict, ...], ...}
    Returns a copy containing only entities/fields worth asking the LLM
    about: fields in SEMANTIC_FIELDS that are still non-empty (nulled-out
    fields, e.g. ones the rule engine already dropped, carry nothing to
    judge; non-semantic fields like case_number/dates have no useful
    check here) and only entities that have at least one such field.
    """
    prepared: dict[str, list[dict]] = {}
    for entity_type, entities in case_entities.items():
        prepared_entities = []
        for idx, entity in enumerate(entities):
            fields = {
                k: v for k, v in entity.items()
                if k in SEMANTIC_FIELDS and v is not None and str(v).strip() != ''
            }
            if fields:
                prepared_entities.append({'index': idx, **fields})
        if prepared_entities:
            prepared[entity_type] = prepared_entities
    return prepared


def _enumerate_fields(prepared_case: dict[str, list[dict]]) -> list[tuple[str, int, str, str]]:
    """Flat, ordered list of every (entity_type, index, field, value) the model must judge."""
    out = []
    for entity_type, entities in prepared_case.items():
        for entity in entities:
            idx = entity['index']
            for field, value in entity.items():
                if field == 'index':
                    continue
                out.append((entity_type, idx, field, value))
    return out

_PROMPT_TEMPLATE = """
You are an expert validator for an Indian Court Case Management System.

Judge whether each field below contains the correct KIND of information for
its field name. Do NOT judge spelling, capitalization, formatting,
abbreviations, or whether a value looks short/unusual — only whether it
belongs in that field at all.

---
## FIELD MEANINGS

name (persons/judges/lawyers/organizations/courts)
Name of a person, company, bank, department, trust, court, or other
entity. Wrong only if clearly not a name (e.g. an address or a role word).

role (persons/lawyers/organizations)
The entity's role in the case. Wrong only if it is clearly a name,
address, designation, court name, or date instead of a role.

address / office_address (persons/lawyers/organizations/courts)
A physical/postal location. Wrong only if it has no location info at all.

designation (judges/lawyers)
A judicial or professional title. May be long/multi-word, e.g. "Additional
District and Sessions Judge" — that is VALID. Wrong only if there is no
title/role word in it at all (e.g. it's just a name or a place).

district
A judicial/administrative district name. Wrong only if it's clearly a
state, full address, court name, or person/org name instead.

state
An Indian state or union territory name. Wrong only if it's clearly a
district, full address, court name, or person/org name instead.

purpose (hearings)
The stage/procedural reason for a hearing. Often a single short word or
abbreviation, e.g. "Report", "Disposed", "SR/Objection" — that is VALID.
Wrong only if it is clearly a person's name, an address, or unrelated text.

nature_of_disposal (hearings)
This field tells how the court case or hearing was concluded or what status/outcome was given to it by the court.
It is a short label describing the result of the hearing, not a description of what happened.
Valid examples: Adjourned, Dismissed, Dismissed In Default, Allowed,Rejected, Withdrawn, Settled, Disposed Of
Invalid examples:
- The case was dismissed because the petitioner did not appear before the court.
- Court gave time to the respondent to submit documents and fixed another hearing date.
- The petition was rejected after detailed examination of the evidence.

---
## RULES

1. Judge only whether the value matches the meaning of its field.
2. Ignore spelling, capitalization, formatting, length, and writing style.
3. Judge every field independently — never compare fields to each other.
4. Only mark a field wrong if it is CLEARLY the wrong kind of information.
5. If in doubt, it is valid.

---
## REASON CODES

Use exactly one of these for each invalid field — do not invent new ones:

{reason_codes}

---
## FIELDS TO JUDGE

{numbered_fields}

---
## OUTPUT FORMAT — STRICT JSON, NOTHING ELSE

Return ONE JSON object, no other text, no markdown fences:

{{"checked": {field_count}, "invalid": [{{"n": <number>, "reason": "<reason_code>"}}, ...]}}

- "checked" MUST equal {field_count} (the total number of fields listed above).
- "invalid" lists ONLY the fields that are wrong. Fields not listed are
  assumed valid.
- If every field is valid, return {{"checked": {field_count}, "invalid": []}}.
"""

def _build_prompt(prepared_case: dict[str, list[dict]], fields: list[tuple[str, int, str, str]]) -> str:
    numbered = "\n".join(
        f"{n} {et}[{idx}].{field} = {value!r}"
        for n, (et, idx, field, value) in enumerate(fields, start=1)
    )
    return _PROMPT_TEMPLATE.format(
        reason_codes=_REASON_CODES_TEXT,
        numbered_fields=numbered,
        field_count=len(fields),
    )


def _normalize_invalid_entries(raw_invalid) -> dict[int, str]:
    """Tolerant extraction of {n: verdict} from whatever shape the model gave 'invalid' as."""
    verdicts: dict[int, str] = {}
    if not isinstance(raw_invalid, list):
        return verdicts
    for entry in raw_invalid:
        if not isinstance(entry, dict):
            continue
        n = entry.get('n')
        if n is None:
            n = entry.get('index') or entry.get('field') or entry.get('number')
        reason = entry.get('reason') or entry.get('verdict') or entry.get('code')
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if not reason:
            continue
        verdicts[n] = str(reason).strip().lower()
    return verdicts


def check_case(case_entities: dict[str, list[dict]], context: str = '') -> list[dict]:
    """
    Run one Ollama call covering the whole case. Returns a list of
    VERIFIED problems: [{'entity_type', 'index', 'field', 'reason'}].
    Every entry has been independently confirmed to correspond to a
    real (entity_type, index, field) that was actually sent to the
    model and still held a value — nothing here is applied on trust
    alone. This function does not mutate anything; see engine.py for
    how the caller turns these into the two output JSONs.
    """
    prepared = build_case_for_prompt(case_entities)
    if not prepared:
        return []

    fields = _enumerate_fields(prepared)
    prompt = _build_prompt(prepared, fields)

    parsed = ask_json(prompt)
    if parsed is None:
        logger.warning(f"[validate_llm] whole-case LLM check unavailable for {context}")
        return []

    checked = parsed.get('checked')
    if checked != len(fields):
        # One retry — small models occasionally drop/duplicate a field on
        # the first pass. If it still doesn't match, the response can't
        # be trusted to be complete, so skip rather than risk silently
        # missing (or hallucinating) a problem.
        logger.warning(
            f"[validate_llm] checked={checked!r} != expected={len(fields)} "
            f"for {context} — retrying once"
        )
        parsed = ask_json(prompt)
        if parsed is None or parsed.get('checked') != len(fields):
            logger.warning(
                f"[validate_llm] whole-case LLM check count mismatch persisted "
                f"for {context} — skipping"
            )
            return []

    verdicts = _normalize_invalid_entries(parsed.get('invalid'))

    problems = []
    for n, (entity_type, idx, field, _value) in enumerate(fields, start=1):
        verdict = verdicts.get(n)
        if verdict is None or verdict == 'valid':
            continue

        # ── Closed-vocabulary backstop ───────────────────────────────
        # If the model invents a code outside our set, it did not
        # correctly identify a real problem — treat the field as valid
        # rather than flagging it. A hallucinated code can feed into
        # whole-entity drops for primary fields (see main.py), so
        # trusting it is too risky.
        reason = _REASON_CODES.get(verdict)
        if reason is None:
            logger.warning(
                f"[validate_llm] unknown verdict code {verdict!r} for "
                f"{entity_type}[{idx}].{field} ({context}) — treating as valid"
            )
            continue

        problems.append({
            'entity_type': entity_type,
            'index': idx,
            'field': field,
            'reason': reason,
        })

    return problems
