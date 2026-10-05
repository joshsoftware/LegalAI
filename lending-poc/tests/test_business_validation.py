"""Tests for the missing-salary-slip reporting in business_validation.

A salary slip is evidence for exactly one month: its own. When a bank
statement covers months the applicant submitted no slip for, those months are
REPORTED as missing (SALARY_CONTINUITY) -- never checked against a
neighbouring slip's declared salary, and never allowed to claim a bank credit.
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
SALARY = 50000.0


def _slip(doc_id, month, salary=SALARY, employer=EMPLOYER):
    """Build a salary slip for a test case.

    Args:
        doc_id (str): Identifier the slip's validation results are keyed by.
        month (date or None): First-of-month salary month, or None for an
            undated slip.
        salary (float): Declared net salary. Defaults to SALARY.
        employer (str): Employer name on the slip. Defaults to EMPLOYER.

    Returns:
        SalarySlipDoc: The constructed slip.
    """
    return SalarySlipDoc(
        doc_id=doc_id, employer_name=employer, net_salary=salary, salary_month=month
    )


def _txn(day, amount=SALARY, narration="NEFT ACME CORP SALARY"):
    """Build a bank transaction that looks like a salary credit by default.

    Args:
        day (date): Transaction date.
        amount (float): Credited amount. Defaults to SALARY.
        narration (str): Bank narration text, matched against the employer.

    Returns:
        BankTransaction: The constructed transaction.
    """
    return BankTransaction(narration=narration, amount=amount, txn_date=day)


def _case(slips, transactions):
    """Build a case holding only salary slips and a bank statement.

    Args:
        slips (list[SalarySlipDoc]): The case's salary slips.
        transactions (list[BankTransaction]): The bank statement's transactions.

    Returns:
        CaseInput: The constructed case.
    """
    return CaseInput(
        applicant_ref="APP-TEST-0001",
        salary_slips=slips,
        bank_statement=BankStatementDoc(transactions=transactions),
    )


def _missing(results):
    """Select the missing-slip results.

    Args:
        results (list[ValidationResult]): Output of run_business_validation.

    Returns:
        list[ValidationResult]: Only the SALARY_CONTINUITY results.
    """
    return [r for r in results if r.check_type == CheckType.SALARY_CONTINUITY]


def _missing_months(results):
    """Collect the months reported as having no salary slip.

    Args:
        results (list[ValidationResult]): Output of run_business_validation.

    Returns:
        set[date]: First-of-month dates from each missing-slip result.
    """
    return {r.evidence["month"] for r in _missing(results)}


def _salary_date(results, doc_id):
    """Find the SALARY_DATE result for one slip.

    Args:
        results (list[ValidationResult]): Output of run_business_validation.
        doc_id (str): The slip whose result to find.

    Returns:
        ValidationResult: That slip's SALARY_DATE result.

    Raises:
        StopIteration: If no SALARY_DATE result exists for doc_id.
    """
    return next(
        r for r in results if r.check_type == CheckType.SALARY_DATE and r.document_id == doc_id
    )


def _matched_transactions(results):
    """Collect every bank transaction some slip claimed as its salary credit.

    Args:
        results (list[ValidationResult]): Output of run_business_validation.

    Returns:
        list[BankTransaction]: One entry per claim, so a transaction claimed
            twice would appear twice.
    """
    return [
        r.evidence["matched_transaction"]
        for r in results
        if r.evidence and "matched_transaction" in r.evidence
    ]


def test_statement_months_without_a_slip_are_reported():
    """Jan and Jun slips against a Jan-Aug statement: Feb-May and Jul are
    reported missing, attributed to no document. Aug is the final month and
    is never required."""
    case = _case(
        [_slip("SLIP-JAN", date(2026, 1, 1)), _slip("SLIP-JUN", date(2026, 6, 1))],
        [_txn(date(2026, 1, 15)), _txn(date(2026, 6, 15)), _txn(date(2026, 8, 31))],
    )

    results = run_business_validation(case)

    assert _missing_months(results) == {
        date(2026, 2, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 7, 1),
    }
    for result in _missing(results):
        assert not result.passed
        assert result.score == 0.0
        assert result.failure_reason == "no_salary_slip_for_month"
        # No slip exists for the month, so there is no document to blame.
        assert result.document_id is None


def test_a_credit_in_an_uncovered_month_is_not_claimed_by_any_slip():
    """The core of the revert: a March credit is no longer pulled in as
    evidence for the January slip (or for anything else). A slip matches
    only inside its own window."""
    jan_credit = _txn(date(2026, 1, 15))
    march_credit = _txn(date(2026, 3, 31))
    case = _case([_slip("SLIP-JAN", date(2026, 1, 1))], [jan_credit, march_credit])

    results = run_business_validation(case)

    jan = _salary_date(results, "SLIP-JAN")
    assert jan.passed
    assert jan.evidence["matched_transaction"] is jan_credit

    # The March credit is evidence for nothing -- it is outside January's
    # window (Dec 27 -> Feb 28) and no other slip exists to claim it.
    assert march_credit not in _matched_transactions(results)
    # March is the statement's final month, so only February is missing.
    assert _missing_months(results) == {date(2026, 2, 1)}


def test_each_credit_can_be_claimed_by_only_one_slip():
    """March's and April's windows overlap (Feb 24 - Apr 30 vs Mar 27 - May
    31), so one credit sits in both. It may prove only one month of income:
    the earlier slip claims it and the later slip fails."""
    only_credit = _txn(date(2026, 4, 2))
    case = _case(
        [_slip("SLIP-MAR", date(2026, 3, 1)), _slip("SLIP-APR", date(2026, 4, 1))],
        [only_credit],
    )

    results = run_business_validation(case)

    march = _salary_date(results, "SLIP-MAR")
    april = _salary_date(results, "SLIP-APR")
    assert march.passed and march.evidence["matched_transaction"] is only_credit
    assert not april.passed
    assert april.failure_reason == "no_matching_credit_in_window"

    assert _matched_transactions(results).count(only_credit) == 1

    credit_count = next(r for r in results if r.check_type == CheckType.SALARY_CREDIT_COUNT)
    assert credit_count.score == 50.0


def test_no_results_when_every_statement_month_has_a_slip():
    """A Mar-Jun statement with a slip for every month reports nothing missing."""
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
        _txn(date(2026, 6, 30)),
    ]

    results = run_business_validation(_case(slips, transactions))

    assert _missing(results) == []


def test_trailing_partial_month_is_not_reported_missing():
    """The common real case: a statement pulled on Sept 16 covering Mar-Sept,
    with slips through August. September's slip has not been issued yet --
    the month is not over -- so it must not be called missing."""
    slips = [_slip(f"SLIP-{m}", date(2026, m, 1)) for m in range(3, 9)]  # Mar..Aug
    transactions = [
        _txn(date(2026, 3, 16)),
        _txn(date(2026, 4, 5)),
        _txn(date(2026, 5, 5)),
        _txn(date(2026, 6, 5)),
        _txn(date(2026, 7, 5)),
        _txn(date(2026, 8, 5)),
        _txn(date(2026, 9, 16)),  # statement ends mid-September
    ]

    results = run_business_validation(_case(slips, transactions))

    assert _missing(results) == []


def test_full_final_month_is_not_reported_missing():
    """Even when the statement runs to Sept 30, September is the final month
    and is never required -- the slip may still not be in hand when the
    statement is pulled."""
    slips = [_slip(f"SLIP-{m}", date(2026, m, 1)) for m in range(3, 9)]  # Mar..Aug
    transactions = [
        _txn(date(2026, 3, 16)),
        _txn(date(2026, 4, 5)),
        _txn(date(2026, 5, 5)),
        _txn(date(2026, 6, 5)),
        _txn(date(2026, 7, 5)),
        _txn(date(2026, 8, 5)),
        _txn(date(2026, 9, 30)),  # statement runs to the end of September
    ]

    results = run_business_validation(_case(slips, transactions))

    assert _missing(results) == []


def test_slip_without_a_salary_month_covers_nothing():
    """An undated slip says nothing about which month it belongs to, so it
    cannot mark any month as covered -- and still fails its own check."""
    undated = SalarySlipDoc(
        doc_id="SLIP-UNDATED", employer_name=EMPLOYER, net_salary=SALARY, salary_month=None
    )
    # The April txn makes April the final (exempt) month, so March is checked.
    case = _case([undated], [_txn(date(2026, 3, 2)), _txn(date(2026, 4, 5))])

    results = run_business_validation(case)

    assert _salary_date(results, "SLIP-UNDATED").failure_reason == "missing_salary_month"
    assert _missing_months(results) == {date(2026, 3, 1)}


def test_single_month_statement_reports_nothing():
    """A statement covering only March has March as its final month, so no
    month is left to require a slip for -- even though no March slip exists.
    (A slip for some other month is needed only because validation is
    skipped entirely for a case with no slips.)"""
    case = _case(
        [_slip("SLIP-JAN", date(2026, 1, 1))],
        [_txn(date(2026, 3, 1)), _txn(date(2026, 3, 31))],
    )

    results = run_business_validation(case)

    assert _missing(results) == []


def test_statement_with_no_transactions_produces_no_results():
    """With no transaction dates there is no statement period to measure, so
    no month can be called missing."""
    results = run_business_validation(_case([_slip("SLIP-JAN", date(2026, 1, 1))], []))

    assert _missing(results) == []


def test_matched_slip_evidence_describes_slip_and_credit():
    """Every result carries source/target documents, values and a message
    so the UI can explain it without knowing the check type."""
    case = _case([_slip("SALARY_SLIP-0", date(2026, 3, 1))], [_txn(date(2026, 4, 1))])

    results = run_business_validation(case)

    salary = _salary_date(results, "SALARY_SLIP-0")
    assert salary.evidence["source_document"] == "SALARY_SLIP-0"
    assert salary.evidence["source_value"] == "₹50,000 for Mar 2026"
    assert salary.evidence["target_document"] == "BANK_STATEMENT"
    assert salary.evidence["target_value"] == "₹50,000 on 01 Apr 2026"
    assert salary.evidence["message"] == "Salary for Mar 2026 was credited on 01 Apr 2026 (₹50,000)."

    employer = next(r for r in results if r.check_type == CheckType.EMPLOYER)
    assert employer.evidence["source_value"] == EMPLOYER
    assert employer.evidence["target_value"] == "NEFT ACME CORP SALARY"


def test_unmatched_slip_evidence_names_the_search_window():
    case = _case([_slip("SALARY_SLIP-0", date(2026, 3, 1))], [_txn(date(2026, 3, 5), amount=1.0)])

    salary = _salary_date(run_business_validation(case), "SALARY_SLIP-0")

    assert salary.evidence["target_value"] is None
    assert salary.evidence["message"] == (
        "No credit of about ₹50,000 was found on the Bank Statement "
        "between 24 Feb 2026 and 30 Apr 2026."
    )


def test_every_business_result_has_a_message():
    """Covers SALARY_CREDIT_COUNT and SALARY_CONTINUITY too, which have no slip."""
    case = _case(
        [_slip("SALARY_SLIP-0", date(2026, 1, 1))],
        [_txn(date(2026, 1, 15)), _txn(date(2026, 3, 31))],
    )

    results = run_business_validation(case)

    assert all(r.evidence and r.evidence["message"] for r in results)
    missing = _missing(results)[0]
    assert missing.evidence["message"] == (
        "The Bank Statement covers Feb 2026, but no salary slip was submitted for that month."
    )
