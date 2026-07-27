"""
Extraction/validate_llm/rules.py
Reusable rule primitives for field-level validation.

Each rule is a callable: (value) -> bool (True = valid, False = drop).
`value` is never None here — the engine skips None/empty values before
calling rules, since "missing" is not the same failure as "wrong".
"""
import re
from Extraction.utils.helpers import parse_date


def is_int(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    try:
        int(str(v).strip())
        return True
    except (TypeError, ValueError):
        return False


def is_float(v) -> bool:
    if isinstance(v, bool):
        return False
    try:
        float(str(v).strip())
        return True
    except (TypeError, ValueError):
        return False


def is_bool(v) -> bool:
    if isinstance(v, bool):
        return True
    return str(v).strip().lower() in ('true', 'false', 'yes', 'no')


def in_range(lo, hi):
    def _check(v) -> bool:
        if not is_float(v):
            return False
        return lo <= float(v) <= hi
    return _check


def regex(pattern: str, flags=0):
    compiled = re.compile(pattern, flags)
    def _check(v) -> bool:
        return bool(compiled.fullmatch(str(v).strip()))
    return _check


def valid_date(v) -> bool:
    return parse_date(v) is not None


def max_length(n: int):
    def _check(v) -> bool:
        return len(str(v).strip()) <= n
    return _check


def one_of(*choices):
    lowered = {c.lower() for c in choices}
    def _check(v) -> bool:
        return str(v).strip().lower() in lowered
    return _check


def all_of(*checks):
    def _check(v) -> bool:
        return all(c(v) for c in checks)
    return _check
