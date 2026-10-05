"""Tests for the display helpers that build user-facing check evidence."""

from datetime import date

from app.services.evidence_format import doc_label, format_date, format_inr, format_month


def test_doc_label_humanises_known_ids():
    assert doc_label("AADHAAR") == "Aadhaar"
    assert doc_label("BANK_STATEMENT") == "Bank Statement"


def test_doc_label_numbers_salary_slips_from_one():
    """'Salary Slip 0' reads like a bug to a user, so slips count from 1."""
    assert doc_label("SALARY_SLIP-0") == "Salary Slip 1"
    assert doc_label("SALARY_SLIP-2") == "Salary Slip 3"


def test_doc_label_falls_back_to_raw_id():
    assert doc_label("SOMETHING_NEW") == "SOMETHING_NEW"
    assert doc_label(None) == "Unknown document"


def test_format_inr_uses_indian_grouping():
    assert format_inr(850) == "₹850"
    assert format_inr(85000) == "₹85,000"
    assert format_inr(150000) == "₹1,50,000"
    assert format_inr(12345678) == "₹1,23,45,678"


def test_format_inr_shows_paise_only_when_present():
    assert format_inr(85000.0) == "₹85,000"
    assert format_inr(85000.5) == "₹85,000.50"
    assert format_inr(None) is None


def test_date_formatters():
    assert format_month(date(2026, 3, 1)) == "Mar 2026"
    assert format_date(date(2026, 4, 1)) == "01 Apr 2026"
    assert format_date(None) is None
