"""Tests for the SALARY_CONTINUITY gap-filling logic in business_validation.

When a bank statement covers more months than the applicant submitted salary
slips for, the uncovered months should still get checked: each gap between
two consecutive slips' own windows is the responsibility of the earlier
slip, and the latest slip is additionally responsible for every month from
the end of its own window through the end of the statement. These checks
must never change an existing slip's own SALARY_DATE result.
"""

from datetime import date

from app.services.business_validation import run_business_validation
from app.services.dto import (
    BankStatementDoc,
    BankTransaction,
    CaseInput,
    CheckType,
    SalarySlipDoc,
)

EMPLOYER = "ACME CORP"


def _slip(doc_id, month, salary=50000.0, employer=EMPLOYER):
    return SalarySlipDoc(doc_id=doc_id, employer_name=employer, net_salary=salary, salary_month=month)


def _txn(day, amount=50000.0, narration="NEFT ACME CORP SALARY"):
    return BankTransaction(narration=narration, amount=amount, txn_date=day)


def _case(slips, transactions):
    return CaseInput(
        applicant_ref="APP-TEST-0001",
        salary_slips=slips,
        bank_statement=BankStatementDoc(transactions=transactions),
    )


def _continuity(results):
    return [r for r in results if r.check_type == CheckType.SALARY_CONTINUITY]


def _salary_date(results, doc_id):
    return next(r for r in results if r.check_type == CheckType.SALARY_DATE and r.document_id == doc_id)


def test_gap_assigned_to_earlier_slip_and_trailing_gap_to_latest_slip():
    jan_slip = _slip("SLIP-JAN", date(2026, 1, 1))
    jun_slip = _slip("SLIP-JUN", date(2026, 6, 1))

    transactions = [
        _txn(date(2026, 1, 15)),  # Jan slip's own window match
        _txn(date(2026, 3, 5)),  # gap month, owned by Jan slip -> matches
        _txn(date(2026, 4, 5)),  # gap month, owned by Jan slip -> matches
        # May: no transaction at all -> gap month should still be reported, failing
        _txn(date(2026, 6, 15)),  # Jun slip's own window match
        _txn(date(2026, 8, 5)),  # trailing gap, owned by Jun slip -> matches
    ]
    case = _case([jan_slip, jun_slip], transactions)

    results = run_business_validation(case)

    # Existing SALARY_DATE results are unaffected by the new checks.
    jan_date = _salary_date(results, "SLIP-JAN")
    jun_date = _salary_date(results, "SLIP-JUN")
    assert jan_date.passed and jan_date.evidence["matched_transaction"].txn_date == date(2026, 1, 15)
    assert jun_date.passed and jun_date.evidence["matched_transaction"].txn_date == date(2026, 6, 15)

    continuity = {r.evidence["month"]: r for r in _continuity(results)}
    assert set(continuity) == {date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1), date(2026, 8, 1)}

    assert continuity[date(2026, 3, 1)].passed
    assert continuity[date(2026, 3, 1)].document_id == "SLIP-JAN"
    assert continuity[date(2026, 4, 1)].passed
    assert continuity[date(2026, 4, 1)].document_id == "SLIP-JAN"

    may_result = continuity[date(2026, 5, 1)]
    assert not may_result.passed
    assert may_result.document_id == "SLIP-JAN"
    assert may_result.failure_reason == "no_matching_credit_in_month"

    aug_result = continuity[date(2026, 8, 1)]
    assert aug_result.passed
    assert aug_result.document_id == "SLIP-JUN"


def test_single_slip_covers_trailing_months_to_statement_end():
    slip = _slip("SLIP-ONLY", date(2026, 1, 1))
    transactions = [
        _txn(date(2026, 1, 15)),
        _txn(date(2026, 5, 20)),
    ]
    case = _case([slip], transactions)

    results = run_business_validation(case)

    continuity_months = {r.evidence["month"] for r in _continuity(results)}
    assert continuity_months == {date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)}
    assert all(r.document_id == "SLIP-ONLY" for r in _continuity(results))


def test_no_gap_when_consecutive_windows_already_cover_the_statement():
    slips = [
        _slip("SLIP-MAR", date(2026, 3, 1)),
        _slip("SLIP-APR", date(2026, 4, 1)),
        _slip("SLIP-MAY", date(2026, 5, 1)),
        _slip("SLIP-JUN", date(2026, 6, 1)),
    ]
    transactions = [
        _txn(date(2026, 3, 10)),
        _txn(date(2026, 4, 10)),
        _txn(date(2026, 5, 10)),
        _txn(date(2026, 7, 4)),  # inside June slip's own window (through Jul 31)
    ]
    case = _case(slips, transactions)

    results = run_business_validation(case)

    assert _continuity(results) == []


def test_gap_month_with_anchor_slip_missing_net_salary():
    jan_slip = SalarySlipDoc(doc_id="SLIP-JAN", employer_name=EMPLOYER, net_salary=None, salary_month=date(2026, 1, 1))
    jun_slip = _slip("SLIP-JUN", date(2026, 6, 1))
    transactions = [_txn(date(2026, 6, 15))]
    case = _case([jan_slip, jun_slip], transactions)

    results = run_business_validation(case)

    jan_gap_results = [r for r in _continuity(results) if r.document_id == "SLIP-JAN"]
    assert jan_gap_results  # gap months were still detected and reported
    assert all(not r.passed for r in jan_gap_results)
    assert all(r.failure_reason == "anchor_slip_missing_net_salary" for r in jan_gap_results)


def test_no_bank_transactions_produces_no_trailing_continuity_checks():
    slip = _slip("SLIP-ONLY", date(2026, 1, 1))
    case = _case([slip], [])

    results = run_business_validation(case)

    assert _continuity(results) == []
