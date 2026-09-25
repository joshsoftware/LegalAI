"""Format-tolerance tests for the POST /cases value normalizers.

The parametrized tables are the real specification of what the endpoint
accepts. Cases marked as rejections matter as much as the accepted ones --
the whole design rests on unparseable values raising rather than quietly
becoming None (see value_normalization's module docstring for why a silent
None turns into a wrong lending decision).
"""

from datetime import date

import pytest

from app.services.value_normalization import (
    ValueFormatError,
    normalize_amount,
    normalize_date,
    normalize_year_month,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Canonical
        ("1995-03-14", date(1995, 3, 14)),
        ("  2026-04-01  ", date(2026, 4, 1)),
        # Day-first, unambiguous (day > 12)
        ("14-03-1995", date(1995, 3, 14)),
        ("14/03/1995", date(1995, 3, 14)),
        ("19-08-1994", date(1994, 8, 19)),
        ("19/08/1994", date(1994, 8, 19)),
        # Ambiguous -- resolved by AMBIGUOUS_DATE_ORDER = DAY_FIRST
        ("03/04/2026", date(2026, 4, 3)),
        # Year-first
        ("2026/03/14", date(2026, 3, 14)),
        ("2026.03.14", date(2026, 3, 14)),
        ("2026-3-1", date(2026, 3, 1)),
        # Month-first forced by evidence (25 cannot be a month)
        ("12/25/2026", date(2026, 12, 25)),
        # Textual months
        ("14 March 1995", date(1995, 3, 14)),
        ("14-Mar-1995", date(1995, 3, 14)),
        ("March 14, 2026", date(2026, 3, 14)),
        ("14 Sept 2026", date(2026, 9, 14)),
        # OCR artefacts that carry no ambiguity
        ("1 4 / 0 3 / 1995", date(1995, 3, 14)),
        ("DOB: 14/03/1995", date(1995, 3, 14)),
        # Passthrough
        (date(1995, 3, 14), date(1995, 3, 14)),
    ],
)
def test_normalize_date_accepts(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("2026-03", "unrecognised_date_format"),  # a month is not a date
        ("March 2026", "unrecognised_date_format"),
        ("14-03-95", "ambiguous_two_digit_year"),
        ("31-02-2026", "not_a_calendar_date"),
        ("32/01/2026", "not_a_calendar_date"),
        ("14-03/1995", "unrecognised_date_format"),  # mixed separators
        ("l4/03/1995", "unrecognised_date_format"),  # no OCR repair on dates
        ("0219-03-14", "year_out_of_range"),
        ("Marhc 14, 2026", "unrecognised_month_name"),
        ("", "empty_value"),
        ("   ", "empty_value"),
        ("N/A", "empty_value"),
        ("-", "empty_value"),
        ("garbage", "unrecognised_date_format"),
        (75000, "wrong_type"),
    ],
)
def test_normalize_date_rejects(raw, reason):
    with pytest.raises(ValueFormatError) as excinfo:
        normalize_date(raw)
    assert excinfo.value.reason == reason


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03", date(2026, 3, 1)),
        ("2026/03", date(2026, 3, 1)),
        ("2026-3", date(2026, 3, 1)),
        ("03-2026", date(2026, 3, 1)),
        ("03/2026", date(2026, 3, 1)),
        # The frontend mapper's bug: a full date in a year-month slot.
        ("2026-03-01", date(2026, 3, 1)),
        ("2026-03-31", date(2026, 3, 1)),
        ("01/03/2026", date(2026, 3, 1)),
        # Textual
        ("March 2026", date(2026, 3, 1)),
        ("Aug 2026", date(2026, 8, 1)),
        ("August 2026", date(2026, 8, 1)),
        ("MARCH-2026", date(2026, 3, 1)),
        ("Mar/2026", date(2026, 3, 1)),
        ("Sept 2026", date(2026, 9, 1)),
        ("2026 March", date(2026, 3, 1)),
        (date(2026, 3, 17), date(2026, 3, 1)),
    ],
)
def test_normalize_year_month_accepts(raw, expected):
    assert normalize_year_month(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "2026-13",  # month out of range
        "2026",  # a bare year is not a month
        "Marhc 2026",  # no fuzzy month matching
        "Q1 2026",
        "FY2026",
        "",
        "garbage",
    ],
)
def test_normalize_year_month_rejects(raw):
    with pytest.raises(ValueFormatError):
        normalize_year_month(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (75000, 75000.0),
        (75000.0, 75000.0),
        ("75000", 75000.0),
        ("75,000", 75000.0),
        ("88,000", 88000.0),
        ("1,23,456", 123456.0),  # Indian lakh grouping
        ("$ 4,500.00", 4500.0),
        ("INR 75,000", 75000.0),
        ("₹75,000", 75000.0),
        ("Rs. 45,000", 45000.0),
        ("Rs 45,000/-", 45000.0),
        ("+75,000", 75000.0),
        ("-18000", -18000.0),
        ("6 ,00 0 . 0 0", 6000.0),  # OCR spacing
        ("(18,000)", -18000.0),  # accounting negative
        ("75,000 Cr", 75000.0),
        ("18,000 Dr", -18000.0),
        ("18,000 DR", -18000.0),
        ("-75,000 Dr", -75000.0),  # idempotent, not double-negated
        ("75.000,00", 75000.0),  # European: last separator is the decimal
    ],
)
def test_normalize_amount_accepts(raw, expected):
    assert normalize_amount(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw",
    [
        True,  # bool subclasses int; must not become 1.0
        False,
        "1.2.3",
        "seventy five thousand",
        "",
        "-",
        "N/A",
        "4,5OO.00",  # OCR repair is off by default -- fail loud
    ],
)
def test_normalize_amount_rejects(raw):
    with pytest.raises(ValueFormatError):
        normalize_amount(raw)


def test_ocr_repair_is_opt_in(monkeypatch):
    """The repair path works when enabled, but is not on by default."""
    monkeypatch.setattr(
        "app.services.value_normalization.REPAIR_OCR_DIGIT_LOOKALIKES", True
    )
    assert normalize_amount("4,5OO.00") == pytest.approx(4500.0)
