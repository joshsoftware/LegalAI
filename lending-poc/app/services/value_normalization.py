"""Tolerant parsing of the date and amount values that reach POST /cases.

The `/cases` contract (docs/cases_api.md) is ISO-canonical: `YYYY-MM-DD`
dates, `YYYY-MM` months, and plain JSON numbers. Nothing upstream enforces
that -- the values originate from an LLM reading a scanned document, so they
arrive written however the document printed them ("14/03/1995", "March 2026",
"Rs. 88,000"). This module converts those into the canonical types.

Two design rules matter more than the parsing itself:

1. **Never return None for a value that was present but unparseable.** A
   None here does not stay a None: a missing `date_of_birth` makes
   `identity_validation` mark the golden record incomplete, which makes
   `decision_engine` return an unconditional FAIL with the score bypassed;
   a missing transaction amount makes `business_validation` drop the
   transaction invisibly, so the matching salary slip then fails
   `no_matching_credit_in_window`. Either way a parse bug would be reported
   as an applicant's fault. Absent-vs-present is the caller's call; present
   but unparseable always raises.

2. **Never guess.** A repaired date is a fabricated identity value, and a
   repaired amount fails *silently* against the 3% match tolerance rather
   than erroring. Where a value is genuinely ambiguous we either resolve it
   on evidence or reject it.

Deliberately stdlib-only and context-free (it knows nothing about documents
or fields) so it stays cheap to unit-test -- importing it must not drag in
app.config, the database, or the sentence-transformers model. `case_parsing`
attaches the document/field context.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Indian KYC documents write dates day-first. This only ever applies to the
# genuinely ambiguous case (both components <= 12); anything decidable is
# decided on evidence below. Named so it is one line to flip and easy to grep.
AMBIGUOUS_DATE_ORDER = "DAY_FIRST"

# Guards against OCR garbage like "0219-03-14" parsing as a valid date.
MIN_PLAUSIBLE_YEAR = 1900
MAX_PLAUSIBLE_YEAR = 2100

# Whether to repair OCR digit lookalikes ("4,5OO.00" -> 4500.00) in amounts.
# Off by default: with SALARY_AMOUNT_TOLERANCE_PCT at 3.0 a mis-repaired
# amount does not error, it just quietly fails to match and scores 0.0 --
# a confidently wrong answer is worse than a loud rejection. Flip to True to
# accept the trade in exchange for fewer rejected cases.
REPAIR_OCR_DIGIT_LOOKALIKES = False


class ValueFormatError(ValueError):
    """A value was present but could not be parsed.

    Subclasses ValueError so existing `except ValueError` handlers still
    catch it. Carries the raw value and a machine-readable reason so the API
    layer can tell the caller exactly which value it choked on.
    """

    def __init__(self, raw: object, expected: str, reason: str) -> None:
        self.raw = raw
        self.expected = expected
        self.reason = reason
        super().__init__(f"{reason}: {raw!r} (expected {expected})")


# Values that mean "nothing here" rather than a malformed value.
_SENTINELS = {"", "-", "--", "n/a", "na", "null", "none", "nil", "nan"}

# Full names plus abbreviations. Built by hand rather than via strptime("%b")
# because %b is locale-dependent and does not accept "Sept".
_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_DATE_EXPECTED = (
    "a date such as 1995-03-14, 14-03-1995, 14/03/1995 or '14 March 1995'"
)
_MONTH_EXPECTED = "a month such as 2026-03, 03/2026 or 'March 2026'"
_AMOUNT_EXPECTED = "a number such as 75000, '75,000' or 'Rs. 75,000.00'"

# Strips a leading field label, e.g. "DOB: 14/03/1995". Safe because we never
# parse times, so a colon in a date value can only be a label separator.
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z ./]*:\s*")

# Three numbers joined by the *same* separator -- the backreference is what
# refuses mixed forms like "14-03/1995".
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,4})\s*([-/.])\s*(\d{1,2})\s*\2\s*(\d{1,4})$")

_TEXT_DMY_RE = re.compile(r"^(\d{1,2})[ \-/]+([A-Za-z]+)[ \-/,]+(\d{4})$")
_TEXT_MDY_RE = re.compile(r"^([A-Za-z]+)[ \-/]+(\d{1,2}),?[ \-/]+(\d{4})$")

_YEAR_MONTH_RE = re.compile(r"^(\d{4})[-/ ](\d{1,2})$")
_MONTH_YEAR_RE = re.compile(r"^(\d{1,2})[-/ ](\d{4})$")
_TEXT_MONTH_YEAR_RE = re.compile(r"^([A-Za-z]+)[ \-/,]+(\d{4})$")
_TEXT_YEAR_MONTH_RE = re.compile(r"^(\d{4})[ \-/,]+([A-Za-z]+)$")


def _clean(value: object, expected: str) -> str:
    """Shared front half of every parser: type check, trim, collapse space."""
    if not isinstance(value, str):
        raise ValueFormatError(value, expected, "wrong_type")
    text = _LABEL_RE.sub("", value.strip())
    # Collapse internal runs of whitespace so OCR spacing ("1 4 / 0 3 / 1995")
    # does not defeat the patterns below.
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in _SENTINELS:
        raise ValueFormatError(value, expected, "empty_value")
    return text


def _build_date(year: int, month: int, day: int, raw: object) -> date:
    if not MIN_PLAUSIBLE_YEAR <= year <= MAX_PLAUSIBLE_YEAR:
        raise ValueFormatError(raw, _DATE_EXPECTED, "year_out_of_range")
    try:
        return date(year, month, day)
    except ValueError as exc:
        # Catches 31-02-2026, 32/01/2026, month 13, etc.
        raise ValueFormatError(raw, _DATE_EXPECTED, "not_a_calendar_date") from exc


def normalize_date(value: object) -> date:
    """Parse a full calendar date. Raises ValueFormatError if it cannot.

    Accepts ISO, the numeric separator forms (day-first or year-first), and
    textual months. Deliberately rejects two-digit years and never applies
    OCR repair -- a date has no redundancy to check a guess against, and
    `matching.exact.dob_match` compares the result with `==`, so a wrong
    guess is reported as an applicant mismatch.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = _clean(value, _DATE_EXPECTED)

    # Fast path for canonical input. Note fromisoformat rejects "2026-03",
    # so a year-month can never slip through here as a day-precise date.
    try:
        return _build_date(*_iso_parts(text), raw=value)
    except _NotIso:
        pass

    # Matched against a fully de-spaced copy so OCR spacing inside the digit
    # groups ("1 4 / 0 3 / 1995") still parses. Safe to always try: a textual
    # form like "14 March 1995" compacts to "14March1995", which this cannot
    # match, so it falls through to the textual branches below unharmed.
    match = _NUMERIC_DATE_RE.match(text.replace(" ", ""))
    if match:
        first, _sep, middle, last = match.group(1), match.group(2), match.group(3), match.group(4)
        if len(first) == 4:
            return _build_date(int(first), int(middle), int(last), value)
        if len(last) != 4:
            # "14-03-95" -- no safe century to pick, and this feeds an
            # equality comparison against the golden record.
            raise ValueFormatError(value, _DATE_EXPECTED, "ambiguous_two_digit_year")
        day, month = _resolve_day_month(int(first), int(middle), value)
        return _build_date(int(last), month, day, value)

    match = _TEXT_DMY_RE.match(text)
    if match:
        month = _month_number(match.group(2), value, _DATE_EXPECTED)
        return _build_date(int(match.group(3)), month, int(match.group(1)), value)

    match = _TEXT_MDY_RE.match(text)
    if match:
        month = _month_number(match.group(1), value, _DATE_EXPECTED)
        return _build_date(int(match.group(3)), month, int(match.group(2)), value)

    raise ValueFormatError(value, _DATE_EXPECTED, "unrecognised_date_format")


class _NotIso(Exception):
    """Internal control-flow marker; never escapes this module."""


def _iso_parts(text: str) -> tuple[int, int, int]:
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise _NotIso from exc
    return parsed.year, parsed.month, parsed.day


def _resolve_day_month(first: int, second: int, raw: object) -> tuple[int, int]:
    """Decide whether a numeric date is day-first or month-first.

    Evidence beats convention: a component above 12 cannot be a month, so it
    settles the order outright. Only when both are <= 12 -- genuinely
    undecidable from the value alone -- do we fall back to the configured
    convention.
    """
    if first > 12 and second <= 12:
        return first, second
    if second > 12 and first <= 12:
        return second, first
    if first > 12 and second > 12:
        raise ValueFormatError(raw, _DATE_EXPECTED, "not_a_calendar_date")
    return (first, second) if AMBIGUOUS_DATE_ORDER == "DAY_FIRST" else (second, first)


def _month_number(name: str, raw: object, expected: str) -> int:
    month = _MONTHS.get(name.strip().lower().rstrip("."))
    if month is None:
        # No fuzzy matching: "Marhc" should fail loudly, not become March.
        raise ValueFormatError(raw, expected, "unrecognised_month_name")
    return month


def normalize_year_month(value: object) -> date:
    """Parse a salary month, returned as the first of that month.

    `SalarySlipDoc.salary_month` is documented as first-of-month, and
    `business_validation._month_window` rebuilds the window from
    (year, month) anyway -- it discards the day. So accepting a full date
    here and truncating it loses no precision, and it is what lets a
    field-mapping result like "2026-03-01" through.
    """
    if isinstance(value, datetime):
        return value.date().replace(day=1)
    if isinstance(value, date):
        return value.replace(day=1)

    text = _clean(value, _MONTH_EXPECTED)

    for pattern, year_group, month_group in (
        (_YEAR_MONTH_RE, 1, 2),
        (_MONTH_YEAR_RE, 2, 1),
    ):
        match = pattern.match(text)
        if match:
            return _build_month(
                int(match.group(year_group)), int(match.group(month_group)), value
            )

    for pattern, year_group, name_group in (
        (_TEXT_MONTH_YEAR_RE, 2, 1),
        (_TEXT_YEAR_MONTH_RE, 1, 2),
    ):
        match = pattern.match(text)
        if match:
            month = _month_number(match.group(name_group), value, _MONTH_EXPECTED)
            return _build_month(int(match.group(year_group)), month, value)

    # Last resort: a full date in any accepted form, truncated to its month.
    try:
        return normalize_date(value).replace(day=1)
    except ValueFormatError as exc:
        raise ValueFormatError(value, _MONTH_EXPECTED, exc.reason) from exc


def _build_month(year: int, month: int, raw: object) -> date:
    if not 1 <= month <= 12:
        raise ValueFormatError(raw, _MONTH_EXPECTED, "month_out_of_range")
    if not MIN_PLAUSIBLE_YEAR <= year <= MAX_PLAUSIBLE_YEAR:
        raise ValueFormatError(raw, _MONTH_EXPECTED, "year_out_of_range")
    return date(year, month, 1)


_CURRENCY_SYMBOL_RE = re.compile(r"[₹$€£¥]")
_CURRENCY_WORD_RE = re.compile(
    r"\b(?:INR|RS|USD|EUR|AED|RUPEES?|DOLLARS?)\b\.?", re.IGNORECASE
)
_CR_DR_RE = re.compile(r"(?:^|\s)(CR|DR)\.?(?:\s|$)", re.IGNORECASE)
_TRAILING_DASH_RE = re.compile(r"/-\s*$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
# Only digits and unambiguous digit lookalikes -- a string of just these has
# no plausible non-numeric reading, which is what makes repair defensible.
_OCR_REPAIRABLE_RE = re.compile(r"^[0-9OolI.,]+$")
_OCR_TRANSLATION = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"})


def normalize_amount(value: object) -> float:
    """Parse a money amount into a float. Raises ValueFormatError if it cannot.

    Handles currency symbols and codes, thousands separators (both US
    1,234,567 and Indian 12,34,567 grouping), accounting parentheses,
    Cr/Dr markers, and the internal whitespace OCR sprinkles through numbers.
    """
    # bool before int: bool subclasses int, so float(True) would silently
    # become an amount of 1.
    if isinstance(value, bool):
        raise ValueFormatError(value, _AMOUNT_EXPECTED, "wrong_type")
    if isinstance(value, (int, float)):
        return float(value)

    text = _clean(value, _AMOUNT_EXPECTED)

    # Cr/Dr is a direction marker, not part of the number.
    marker_sign = 0
    marker = _CR_DR_RE.search(text)
    if marker:
        marker_sign = -1 if marker.group(1).upper() == "DR" else 1
        text = _CR_DR_RE.sub(" ", text)

    # Currency removal must precede whitespace removal: "INR 75,000" collapsed
    # to "INR75,000" would no longer match the \b word boundary.
    text = _CURRENCY_SYMBOL_RE.sub("", text)
    text = _CURRENCY_WORD_RE.sub("", text)
    text = _TRAILING_DASH_RE.sub("", text)
    text = re.sub(r"\s+", "", text)

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.startswith(("+", "-")):
        negative = negative or text.startswith("-")
        text = text[1:]

    text = _strip_group_separators(text)

    amount = _to_float(text)
    if amount is None and REPAIR_OCR_DIGIT_LOOKALIKES and _OCR_REPAIRABLE_RE.match(text):
        repaired = _strip_group_separators(text.translate(_OCR_TRANSLATION))
        amount = _to_float(repaired)
        if amount is not None:
            logger.warning("Repaired OCR digit lookalikes in amount %r -> %r", value, repaired)
    if amount is None:
        raise ValueFormatError(value, _AMOUNT_EXPECTED, "unrecognised_amount_format")

    if negative:
        amount = -amount
    if marker_sign:
        # abs() keeps this idempotent: "-75,000 Dr" stays -75000 rather than
        # being negated a second time.
        amount = -abs(amount) if marker_sign < 0 else abs(amount)
    return amount


def _strip_group_separators(text: str) -> str:
    """Resolve which of '.' and ',' is the decimal point.

    Whichever appears last is the decimal separator; the other is grouping.
    A lone comma is treated as grouping, which is the Indian/US reading --
    so "6,00" is 600, not the European 6.00. Ambiguous by nature; grouping is
    overwhelmingly the more common intent in this corpus.
    """
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if "," in text:
        return text.replace(",", "")
    return text


def _to_float(text: str) -> float | None:
    # The regex gate is what rejects "1.2.3" and stray characters that
    # float() would either accept surprisingly or fail on unhelpfully.
    if not _PLAIN_NUMBER_RE.match(text):
        return None
    return float(text)
