"""
Extraction/validate_llm/field_rules.py
Declarative per-entity, per-field validation rules.

Each entity maps field_name -> list of rule callables (see rules.py).
A field with no entry here is passed through unchecked (free-text fields
like `name`, `address`, `description`, `search_summary`, etc. have no
reliable rule and are left for the future LLM-review step).

To add a rule: add/extend the field's list. To add an entity: add a new
top-level dict and register it in ENTITY_RULES.
"""
from Extraction.validate_llm.rules import (
    is_int, is_float, is_bool, in_range, regex, valid_date, one_of,
)

CURRENT_YEAR = 2026

USER_RULES = {
    'aadhaar_no': [regex(r'\d{12}')],
    'pan_no'    : [regex(r'[A-Za-z]{5}\d{4}[A-Za-z]')],
    'age'       : [is_int, in_range(0, 120)],
    'gender'    : [one_of('male', 'female', 'other')],
}

JUDGE_RULES = {
    'heard_from_date': [valid_date],
    'heard_to_date'  : [valid_date],
    'status'         : [one_of('active', 'retired', 'transferred')],
}

LAWYER_RULES = {
    'enrollment_date': [valid_date],
}

CASE_RULES = {
    'filing_date'        : [valid_date],
    'disposal_date'      : [valid_date],
    'registration_date'  : [valid_date],
    'first_hearing_date' : [valid_date],
    'last_hearing_date'  : [valid_date],
    'next_hearing_date'  : [valid_date],
    'decision_date'      : [valid_date],
    'filing_year'        : [is_int, in_range(1950, CURRENT_YEAR)],
    'in_favour_of'       : [is_bool],
    'alleged_amount'     : [is_float, in_range(0, float('inf'))],
}

ORGANIZATION_RULES = {
    'cin' : [regex(r'[A-Za-z]\d{5}[A-Za-z]{2}\d{4}[A-Za-z]{3}\d{6}')],
    'gstin': [regex(r'\d{2}[A-Za-z]{5}\d{4}[A-Za-z]\d[A-Za-z\d]Z[A-Za-z\d]')],
    'pan' : [regex(r'[A-Za-z]{5}\d{4}[A-Za-z]')],
}

COURT_RULES = {
    'hierarchy_level': [is_int, in_range(0, 10)],
}

ACT_RULES = {
    'year': [is_int, in_range(1800, CURRENT_YEAR)],
}

SECTION_RULES = {
    'bailable': [is_bool],
}

CASE_HEARING_RULES = {
    'date'              : [valid_date],
    'last_hearing_date' : [valid_date],
    'next_hearing_date' : [valid_date],
}

ASSET_RULES = {
    'estimated_value_inr': [is_float, in_range(0, float('inf'))],
}

DOCUMENT_RULES = {
    'order_date': [valid_date],
}

ENTITY_RULES = {
    'user'        : USER_RULES,
    'judge'       : JUDGE_RULES,
    'lawyer'      : LAWYER_RULES,
    'case'        : CASE_RULES,
    'organization': ORGANIZATION_RULES,
    'court'       : COURT_RULES,
    'act'         : ACT_RULES,
    'section'     : SECTION_RULES,
    'case_hearing': CASE_HEARING_RULES,
    'asset'       : ASSET_RULES,
    'document'    : DOCUMENT_RULES,
}
