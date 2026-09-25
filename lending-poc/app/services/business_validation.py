"""Checks employer + salary consistency between salary slips and the bank
statement. No specific payroll day is assumed anywhere: each slip is
matched against bank transactions inside a broad, month-level window.
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


def _calendar_month_range(month: date) -> tuple[date, date]:
    """First and last calendar day of `month` (must be first-of-month)."""
    last_day = monthrange(month.year, month.month)[1]
    return date(month.year, month.month, 1), date(month.year, month.month, last_day)


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


def _gap_months_for_slip(
    slip: SalarySlipDoc,
    next_slip: SalarySlipDoc | None,
    bank_statement: BankStatementDoc,
) -> list[date]:
    """Calendar months `slip` is responsible for under the SALARY_CONTINUITY
    rule: the gap between its own window end and either `next_slip`'s own
    window start (chronologically consecutive pair), or -- when `next_slip`
    is None, meaning `slip` is the latest dated slip -- the end of bank
    statement coverage (the month of the latest txn_date).
    """
    _, window_end = _month_window(slip.salary_month)
    gap_start = window_end + timedelta(days=1)

    if next_slip is not None:
        next_window_start, _ = _month_window(next_slip.salary_month)
        gap_end = next_window_start - timedelta(days=1)
    else:
        txn_dates = [t.txn_date for t in bank_statement.transactions if t.txn_date is not None]
        if not txn_dates:
            return []
        gap_end = max(txn_dates)

    return _split_into_months(gap_start, gap_end)


def _validate_continuity_month(
    slip: SalarySlipDoc,
    month: date,
    bank_statement: BankStatementDoc,
    used_transaction_ids: set[int],
) -> ValidationResult:
    """One SALARY_CONTINUITY result for a single uncovered calendar `month`,
    using `slip` (the responsible slip under the gap-assignment rule) as the
    reference for expected employer/amount. Mirrors _validate_salary_slip's
    matching logic, scoped to one calendar month, sharing the same
    used_transaction_ids set so a credit already claimed elsewhere can't be
    claimed again here.
    """
    if slip.net_salary is None:
        return ValidationResult(
            check_type=CheckType.SALARY_CONTINUITY,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="anchor_slip_missing_net_salary",
            evidence={"month": month},
        )

    month_range = _calendar_month_range(month)
    candidates = [
        txn
        for txn in _candidate_transactions(month_range, bank_statement.transactions, slip.net_salary)
        if id(txn) not in used_transaction_ids
    ]
    selection = _select_best_transaction(candidates, slip.employer_name, slip.net_salary)

    if selection is None:
        return ValidationResult(
            check_type=CheckType.SALARY_CONTINUITY,
            passed=False,
            score=0.0,
            document_id=slip.doc_id,
            failure_reason="no_matching_credit_in_month",
            evidence={"month": month},
        )

    txn, score = selection
    used_transaction_ids.add(id(txn))
    return ValidationResult(
        check_type=CheckType.SALARY_CONTINUITY,
        passed=True,
        score=score,
        document_id=slip.doc_id,
        evidence={"month": month, "matched_transaction": txn},
    )


def _salary_continuity_checks(
    ordered_slips: list[SalarySlipDoc],
    bank_statement: BankStatementDoc,
    used_transaction_ids: set[int],
) -> list[ValidationResult]:
    """Runs after all per-slip SALARY_DATE matching is complete, reusing the
    same used_transaction_ids set so a credit already claimed by a slip's own
    window can't also be claimed here. Slips without a salary_month have no
    window to anchor a gap and are excluded.
    """
    dated_slips = [s for s in ordered_slips if s.salary_month is not None]
    results: list[ValidationResult] = []
    for i, slip in enumerate(dated_slips):
        next_slip = dated_slips[i + 1] if i + 1 < len(dated_slips) else None
        for month in _gap_months_for_slip(slip, next_slip, bank_statement):
            results.append(_validate_continuity_month(slip, month, bank_statement, used_transaction_ids))
    return results


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

    # Runs last so it only claims transactions left over after every slip's
    # own SALARY_DATE match.
    results.extend(_salary_continuity_checks(ordered_slips, case.bank_statement, used_transaction_ids))

    return results
