"""Tests for error aggregation in parse_case.

The behaviour under test is the invariant the rest of the pipeline depends
on: after parse_case returns, a None field means *absent*, never *present
but malformed*. A malformed value must raise, and every malformed value in
the payload must be reported together.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.case_parsing import CaseParseError, parse_case

REPO_ROOT = Path(__file__).resolve().parents[1]


def _payload(*documents, applicant_ref="APP-TEST-0001"):
    return {"applicant_ref": applicant_ref, "documents": list(documents)}


def _aadhaar(**fields):
    return {"doc_type": "AADHAAR", "extracted_fields": fields}


def _pan(**fields):
    return {"doc_type": "PAN", "extracted_fields": fields}


def _salary_slip(*slips):
    return {
        "doc_type": "SALARY_SLIP",
        "salary_slips": [{"extracted_fields": s} for s in slips],
    }


def _bank(*transactions):
    return {
        "doc_type": "BANK_STATEMENT",
        "extracted_fields": {"name": "A", "transactions": list(transactions)},
    }


def test_collects_every_bad_field_in_one_error():
    payload = _payload(
        _aadhaar(name="A", date_of_birth="14-03-95"),  # two-digit year
        _salary_slip({"name": "A", "employer_name": "X", "net_salary": "1.2.3", "salary_month": "Q1 2026"}),
        _bank({"narration": "SAL", "amount": "abc", "date": "2026-04-01"}),
    )

    with pytest.raises(CaseParseError) as excinfo:
        parse_case(payload)

    errors = excinfo.value.errors
    assert len(errors) == 4
    assert [(e.document, e.field) for e in errors] == [
        ("AADHAAR", "date_of_birth"),
        ("SALARY_SLIP-0", "net_salary"),
        ("SALARY_SLIP-0", "salary_month"),
        ("BANK_STATEMENT", "transactions[0].amount"),
    ]


def test_error_echoes_the_offending_value():
    with pytest.raises(CaseParseError) as excinfo:
        parse_case(_payload(_aadhaar(name="A", date_of_birth="14-03-95")))

    (error,) = excinfo.value.errors
    assert error.value == "14-03-95"
    assert error.reason == "ambiguous_two_digit_year"
    assert error.expected  # a non-empty hint for the caller


def test_transaction_indices_are_preserved():
    with pytest.raises(CaseParseError) as excinfo:
        parse_case(
            _payload(
                _bank(
                    {"narration": "ok", "amount": 100, "date": "2026-04-01"},
                    {"narration": "bad", "amount": "abc", "date": "2026-04-02"},
                    {"narration": "ok", "amount": 200, "date": "2026-04-03"},
                    {"narration": "bad", "amount": 300, "date": "not-a-date"},
                )
            )
        )

    assert [e.field for e in excinfo.value.errors] == [
        "transactions[1].amount",
        "transactions[3].date",
    ]


def test_absent_values_are_not_errors():
    """A missing/null/blank field is legitimately absent, not malformed."""
    case = parse_case(
        _payload(_aadhaar(name="A", date_of_birth=None, aadhaar_number="   "))
    )
    assert case.aadhaar.date_of_birth is None
    assert case.aadhaar.aadhaar_number is None


def test_empty_salary_slips_is_aggregated_not_raised_early():
    """The structural error must not pre-empt field errors elsewhere."""
    with pytest.raises(CaseParseError) as excinfo:
        parse_case(
            _payload(
                {"doc_type": "SALARY_SLIP", "salary_slips": []},
                _aadhaar(name="A", date_of_birth="garbage"),
            )
        )

    assert [(e.document, e.reason) for e in excinfo.value.errors] == [
        ("SALARY_SLIP", "no_salary_slips"),
        ("AADHAAR", "unrecognised_date_format"),
    ]


def test_document_formats_are_normalized_to_canonical_types():
    case = parse_case(
        _payload(
            _aadhaar(name="A", aadhaar_number=644676544321, date_of_birth="19/08/1994"),
            _salary_slip(
                {
                    "name": "A",
                    "employer_name": "X",
                    "net_salary": "Rs. 88,000",
                    "salary_month": "March 2026",
                }
            ),
            _bank({"narration": "SAL", "amount": "75,000", "date": "03/04/2026"}),
        )
    )

    assert case.aadhaar.date_of_birth == date(1994, 8, 19)
    # An unquoted all-digit Aadhaar number still arrives as text.
    assert case.aadhaar.aadhaar_number == "644676544321"
    assert case.salary_slips[0].net_salary == pytest.approx(88000.0)
    assert case.salary_slips[0].salary_month == date(2026, 3, 1)
    assert case.bank_statement.transactions[0].amount == pytest.approx(75000.0)
    assert case.bank_statement.transactions[0].txn_date == date(2026, 4, 3)


def test_pan_date_of_birth_is_parsed_and_normalized():
    """PAN cards print a DOB, so it must survive parsing to be cross-checked
    against the Aadhaar DOB during identity validation."""
    case = parse_case(_payload(_pan(name="A", pan_number="ABCDE1234F", date_of_birth="19-Aug-1994")))

    assert case.pan.date_of_birth == date(1994, 8, 19)


def test_malformed_pan_date_of_birth_is_aggregated_like_any_other_field():
    with pytest.raises(CaseParseError) as excinfo:
        parse_case(
            _payload(
                _aadhaar(name="A", date_of_birth="garbage"),
                _pan(name="A", pan_number="ABCDE1234F", date_of_birth="14-03-95"),
            )
        )

    assert [(e.document, e.field, e.reason) for e in excinfo.value.errors] == [
        ("AADHAAR", "date_of_birth", "unrecognised_date_format"),
        ("PAN", "date_of_birth", "ambiguous_two_digit_year"),
    ]


def test_absent_pan_date_of_birth_is_not_an_error():
    """A PAN whose DOB was never extracted stays None rather than failing --
    the field is optional on the wire even though the template requests it."""
    case = parse_case(_payload(_pan(name="A", pan_number="ABCDE1234F")))

    assert case.pan.date_of_birth is None


@pytest.mark.parametrize("sample", ["sample_case.json", "sample_case_clean.json"])
def test_committed_samples_still_parse(sample):
    """Golden regression: the documented ISO payloads must keep working."""
    path = REPO_ROOT / "scripts" / sample
    if not path.exists():
        pytest.skip(f"{sample} not present")
    case = parse_case(json.loads(path.read_text(encoding="utf-8")))
    assert case.applicant_ref
