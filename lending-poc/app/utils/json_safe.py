"""Recursively converts dataclasses/dates/tuples into plain
JSON-serializable values, since validation/scoring build evidence out of
dataclasses (e.g. BankTransaction) and date objects for in-memory use.
"""

import dataclasses
import datetime


def json_safe(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: json_safe(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value
