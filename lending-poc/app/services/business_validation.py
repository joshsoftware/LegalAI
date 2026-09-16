"""Checks employer + salary consistency between salary slips and the bank
statement. No specific payroll day is assumed anywhere: each slip is
matched against bank transactions inside a broad, month-level window.

A slip is evidence for exactly one month -- its own. Statement months with
no submitted slip are reported as missing (SALARY_CONTINUITY) rather than
checked against a neighbouring slip's declared salary, which would let one
slip stand in as income evidence for a month it says nothing about.
"""

from calendar import monthrange
from datetime import date, timedelta

from app.matching.fuzzy import employer_similarity
from app.services import validation_config as cfg
from app.services.dto import (
    BankStatementDoc,
    BankTransaction,
    CaseInput,
    CheckType,
    SalarySlipDoc,
    ValidationResult,
)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _month_window(salary_month: date) -> tuple[date, date]:
    # Payroll dates vary by employer (paid on the 1st, or late into the next
    # month), so instead of expecting an exact date we build a tolerant range:
    # SALARY_CREDIT_BUFFER_DAYS before the salary month starts, through the
    # end of the month SALARY_CREDIT_EXTRA_MONTHS later. E.g. for a March
    # slip with buffer=5, extra=1: Feb 24 -> Apr 30.
    window_start = date(salary_month.year, salary_month.month, 1) - timedelta(
        days=cfg.SALARY_CREDIT_BUFFER_DAYS
    )
    window_end_month = _add_months(salary_month, cfg.SALARY_CREDIT_EXTRA_MONTHS)
    last_day = monthrange(window_end_month.year, window_end_month.month)[1]
    window_end = date(window_end_month.year, window_end_month.month, last_day)
    return window_start, window_end


def _split_into_months(start: date, end: date) -> list[date]:
    """Every calendar month (as first-of-month dates) touched by [start, end],
    inclusive of partial months at both ends. Empty if start > end.
    """
    if start > end:
        return []
    months: list[date] = []
    cursor = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    while cursor <= end_month:
        months.append(cursor)
        cursor = _add_months(cursor, 1)
    return months


def _within_amount_tolerance(amount: float, expected: float) -> bool:
    if not expected:
        return False
    pct_diff = abs(amount - expected) / expected * 100.0
    return pct_diff <= cfg.SALARY_AMOUNT_TOLERANCE_PCT


def _candidate_transactions(
    window: tuple[date, date], transactions: list[BankTransaction], expected_amount: float | None
) -> list[BankTransaction]:
    """Transactions inside the month-window AND within salary-amount
    tolerance of what this specific slip declared. The tolerance gate is
    on amount alone -- a large reimbursement/bonus/advance with a
    coincidentally close amount is excluded here, before narration
    similarity ever gets a vote, so it can never mask a genuinely missing
    salary credit.
    """
    start, end = window
    return [
        txn
        for txn in transactions
        if txn.amount is not None
        and txn.txn_date is not None
        and txn.amount > 0
        and start <= txn.txn_date <= end
        and (expected_amount is None or _within_amount_tolerance(txn.amount, expected_amount))
    ]


def _amount_closeness(amount: float, expected: float) -> float:
    if not expected:
        return 0.0
    closeness = 100.0 * (1 - abs(amount - expected) / expected)
    return max(0.0, min(100.0, closeness))


def _score_transaction(txn: BankTransaction, employer_name: str, expected_amount: float) -> float:
    employer_score = employer_similarity(employer_name, txn.narration) if employer_name else 0.0
    amount_score = _amount_closeness(txn.amount, expected_amount)
    return (
        cfg.TXN_SELECTION_EMPLOYER_WEIGHT * employer_score
        + cfg.TXN_SELECTION_AMOUNT_WEIGHT * amount_score
    )


def _select_best_transaction(
    candidates: list[BankTransaction], employer_name: str | None, expected_amount: float | None
) -> tuple[BankTransaction, float] | None:
    if not candidates or expected_amount is None:
        return None
    scored = [(txn, _score_transaction(txn, employer_name, expected_amount)) for txn in candidates]
    best_txn, best_score = max(scored, key=lambda pair: pair[1])
    if best_score < cfg.TXN_SELECTION_MIN_SCORE:
        return None
    return best_txn, best_score


def _validate_salary_slip(
    slip: SalarySlipDoc, bank_statement: BankStatementDoc, used_transaction_ids: set[int]
) -> ValidationResult:
    """Matches one slip against the bank statement.

    `used_transaction_ids` (by `id(txn)`) tracks credits already claimed by
    an earlier slip in this same case, since overlapping month-windows mean
    the same credit could otherwise be double-counted as evidence for two
    different declared months of income.
    """
    if slip.salary_month is None:
        return ValidationResult(
            check_type=CheckType.SALARY_DATE,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="missing_salary_month",
        )

    if slip.net_salary is None:
        return ValidationResult(
            check_type=CheckType.SALARY_DATE,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="missing_net_salary",
        )

    window = _month_window(slip.salary_month)
    
    #Two filters are applied here:
    # _candidate_transactions keeps only transactions inside that date window and within tolerance of the claimed amount (e.g. within a few % of ₹85,000).
    # The list comprehension then removes any transaction whose id() is already in used_transaction_ids.
    candidates = [
        txn
        for txn in _candidate_transactions(window, bank_statement.transactions, slip.net_salary)
        if id(txn) not in used_transaction_ids
    ]
    selection = _select_best_transaction(candidates, slip.employer_name, slip.net_salary)

    if selection is None:
        return ValidationResult(
            check_type=CheckType.SALARY_DATE,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="no_matching_credit_in_window",
            evidence={"window": window},
        )

    txn, score = selection
    used_transaction_ids.add(id(txn))
    return ValidationResult(
        check_type=CheckType.SALARY_DATE,
        passed=True,
        score=score,
        document_id=slip.doc_id,
        evidence={"matched_transaction": txn},
    )


def _employer_match_for_slip(
    slip: SalarySlipDoc, slip_result: ValidationResult
) -> ValidationResult:
    """Verifies one slip's declared employer against its OWN matched bank
    transaction's narration only — never against another month's slip.

    Employer consistency is judged month-by-month, on purpose: an
    applicant switching jobs mid-history is normal and legitimate, so May's
    employer claim is never compared to June's. Each month stands on its
    own evidence.
    """
    if not slip.employer_name:
        return ValidationResult(
            check_type=CheckType.EMPLOYER,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="missing_employer_name",
        )

    if not slip_result.passed or not slip_result.evidence:
        return ValidationResult(
            check_type=CheckType.EMPLOYER,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="no_matching_credit_to_verify_employer_against",
        )

    matched_txn = slip_result.evidence.get("matched_transaction")
    score = employer_similarity(slip.employer_name, matched_txn.narration)
    passed = score >= cfg.EMPLOYER_MATCH_THRESHOLD
    return ValidationResult(
        check_type=CheckType.EMPLOYER,
        passed=passed,
        score=score,
        document_id=slip.doc_id,
        failure_reason=None if passed else "employer_narration_mismatch",
    )


def _salary_credit_count(
    salary_slips: list[SalarySlipDoc],
    bank_statement: BankStatementDoc,
    slip_results: list[ValidationResult],
) -> ValidationResult:
    total_slips = len(salary_slips)
    matched_slips = sum(1 for r in slip_results if r.passed)
    confidence_score = (matched_slips / total_slips * 100.0) if total_slips else 0.0

    dates = [txn.txn_date for txn in bank_statement.transactions if txn.txn_date is not None]
    stmt_duration = {"start": min(dates), "end": max(dates)} if dates else None

    return ValidationResult(
        check_type=CheckType.SALARY_CREDIT_COUNT,
        passed=(matched_slips == total_slips),
        score=confidence_score,
        evidence={
            "stmt_duration": stmt_duration,
            "no_of_matches": matched_slips,
            "total_slips": total_slips,
            "confidence_score": confidence_score,
        },
    )


def _statement_months(bank_statement: BankStatementDoc) -> list[date]:
    """Calendar months the statement covers, as first-of-month dates.

    A trailing partial month is excluded: the statement was pulled part-way
    through it, so that month's slip has not been issued yet and reporting it
    as missing would penalise an applicant for a document that cannot exist.
    A partial LEADING month is kept -- its slip was issued long ago.

    The period is inferred from transaction dates because BankStatementDoc
    carries no declared statement period (the same inference
    _salary_credit_count makes for stmt_duration). A statement that happens
    to have no transactions in its final days therefore looks partial, which
    errs toward reporting nothing -- the safe direction.
    """
    txn_dates = [t.txn_date for t in bank_statement.transactions if t.txn_date is not None]
    if not txn_dates:
        return []

    last = max(txn_dates)
    months = _split_into_months(min(txn_dates), last)
    if months and last.day < monthrange(last.year, last.month)[1]:
        months.pop()
    return months


def _months_with_a_slip(salary_slips: list[SalarySlipDoc]) -> set[date]:
    """Months the applicant actually submitted a slip for: each slip's own
    salary_month, deliberately NOT its matching window.

    _month_window is wide (buffer days either side, plus an extra month) only
    to tolerate payroll landing late. Reusing it as coverage would convert a
    payment-timing tolerance into an evidence claim, letting a March slip
    vouch for April -- a quieter form of the cross-month matching this check
    replaced.
    """
    return {slip.salary_month for slip in salary_slips if slip.salary_month is not None}


def _missing_slip_checks(
    salary_slips: list[SalarySlipDoc], bank_statement: BankStatementDoc
) -> list[ValidationResult]:
    """One result per statement month with no submitted slip.

    This reports a documentation gap, not a suspicion about income: it makes
    no attempt to infer what the applicant earned in an uncovered month. It
    reads no transactions at all, so it can never claim a bank credit -- a
    slip's own window match stays the only thing that consumes one.
    """
    covered = _months_with_a_slip(salary_slips)
    return [
        ValidationResult(
            check_type=CheckType.SALARY_CONTINUITY,
            passed=False,
            score=0.0,
            document_id=None,  # no slip exists to attribute this to -- that IS the finding
            failure_reason="no_salary_slip_for_month",
            evidence={"month": month},
        )
        for month in _statement_months(bank_statement)
        if month not in covered
    ]


def run_business_validation(case: CaseInput) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    if not case.salary_slips or not case.bank_statement:
        return results

    used_transaction_ids: set[int] = set()
    ordered_slips = sorted(
        case.salary_slips, key=lambda slip: slip.salary_month or date.max
    )
    slip_results_by_doc_id = {
        slip.doc_id: _validate_salary_slip(slip, case.bank_statement, used_transaction_ids)
        for slip in ordered_slips
    }
    # Preserve the original slip order in the output, independent of the
    # chronological order used to resolve which slip claims which credit.
    slip_results = [slip_results_by_doc_id[slip.doc_id] for slip in case.salary_slips]
    results.extend(slip_results)

    for slip in case.salary_slips:
        results.append(_employer_match_for_slip(slip, slip_results_by_doc_id[slip.doc_id]))

    results.append(_salary_credit_count(case.salary_slips, case.bank_statement, slip_results))

    results.extend(_missing_slip_checks(case.salary_slips, case.bank_statement))

    return results
