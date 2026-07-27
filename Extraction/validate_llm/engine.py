"""
Extraction/validate_llm/engine.py
Rule-based validation engine.

Walks a raw entity dict (as returned by the LLM extraction step) against
the declarative rules in field_rules.py. Any field that fails its rule(s)
is nulled out (kept in the dict as None) so the rest of the entity still
gets inserted — matching the codebase's existing to_none()/missing_data_log
convention for "no reliable value".

Fields flagged here are also collected so a future LLM-review step can
pick them up (see FLAGGED_FOR_LLM below) without touching this module.
"""
import logging
from typing import Any

from Extraction.utils.helpers import to_none
from Extraction.validate_llm.field_rules import ENTITY_RULES
from Extraction.validate_llm.llm_field_checks import check_case

logger = logging.getLogger('pipeline')


def validate_entity(entity_type: str, data: dict, context: str = '') -> tuple[dict, list[dict]]:
    """
    Validate one entity dict in place (returns a new dict; input is not mutated).

    Returns (cleaned_data, dropped) where `dropped` is a list of
    {'entity_type', 'field', 'value', 'context'} describing what was nulled.
    """
    rules = ENTITY_RULES.get(entity_type.lower())
    if not rules:
        return data, []

    cleaned = dict(data)
    dropped: list[dict] = []

    for field, checks in rules.items():
        if field not in cleaned:
            continue
        raw_value = to_none(cleaned.get(field))
        if raw_value is None:
            continue

        if not all(check(raw_value) for check in checks):
            dropped.append({
                'entity_type': entity_type,
                'field'      : field,
                'value'      : raw_value,
                'context'    : context,
            })
            cleaned[field] = None

    if dropped:
        for d in dropped:
            logger.warning(
                f"[validate_llm] dropped invalid field "
                f"{d['entity_type']}.{d['field']}={d['value']!r} ({d['context']})"
            )

    return cleaned, dropped


def validate_entities(entity_type: str, items: list[dict], context: str = '') -> tuple[list[dict], list[dict]]:
    """Validate a list of entity dicts (e.g. all judges_data). Returns (cleaned_items, all_dropped)."""
    cleaned_items = []
    all_dropped: list[dict] = []
    for item in items:
        cleaned, dropped = validate_entity(entity_type, item, context)
        cleaned_items.append(cleaned)
        all_dropped.extend(dropped)
    return cleaned_items, all_dropped


def validate_case_llm(case_entities: dict[str, list[dict]], context: str = '') -> tuple[dict[str, list[dict]], list[dict]]:
    """
    Run ONE Ollama call covering the whole case (see llm_field_checks.py)
    — the model is asked to flag any field whose value looks semantically
    wrong for its field name (generic check, not limited to a fixed set
    of fields). Every flagged field is independently re-verified against
    the input before being trusted (see check_case()'s hallucination
    backstop) — nothing is dropped on the model's word alone.

    case_entities: {'persons': [dict, ...], 'judges': [dict, ...], ...}
    (each inner dict must be a plain dict — not a Pydantic model — see
    main.py for the persons->dict / dict->persons conversion at the call site)

    Returns two SEPARATE JSON-serializable structures:
      cleaned_json — same shape as case_entities, with only verified-bad
                     fields nulled; everything else untouched. This is
                     what the next pipeline step / Neo4j insert should
                     read from.
      dropped_json — a flat list of what was removed and why:
                     [{'entity_type', 'index', 'field', 'value',
                       'reason', 'context'}, ...]. This is for logs/
                     testing only — it never feeds back into the data
                     path.
    """
    problems = check_case(case_entities, context)
    if not problems:
        return case_entities, []

    cleaned = {etype: [dict(e) for e in items] for etype, items in case_entities.items()}
    dropped_json: list[dict] = []

    for p in problems:
        entity = cleaned[p['entity_type']][p['index']]
        field = p['field']
        value = entity.get(field)
        dropped_json.append({
            'entity_type': p['entity_type'],
            'index'      : p['index'],
            'field'      : field,
            'value'      : value,
            'reason'     : p['reason'],
            'context'    : context,
        })
        entity[field] = None
        logger.warning(
            f"[validate_llm] LLM dropped invalid field "
            f"{p['entity_type']}[{p['index']}].{field}={value!r} ({context}) — {p['reason']}"
        )

    return cleaned, dropped_json
