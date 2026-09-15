"""Checks employer + salary consistency between salary slips and the bank
statement. No specific payroll day is assumed anywhere: each slip is
matched against bank transactions inside a broad, month-level window.
"""

from calendar import monthrange
from datetime import date, timedelta

from cross_document_validation.matching.fuzzy import employer_similarity
from cross_document_validation.services import validation_config as cfg
from cross_document_validation.services.dto import (
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
    window_start = date(salary_month.year, salary_month.month, 1) - timedelta(
        days=cfg.SALARY_CREDIT_BUFFER_DAYS
    )
    window_end_month = _add_months(salary_month, cfg.SALARY_CREDIT_EXTRA_MONTHS)
    last_day = monthrange(window_end_month.year, window_end_month.month)[1]
    window_end = date(window_end_month.year, window_end_month.month, last_day)
    return window_start, window_end


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
            evidence={
                "source_text": slip.salary_month.strftime("%B %Y"),
                "target_text": None,
                "match_type": "DATE_MATCH",
                "window": window,
            },
        )

    txn, score = selection
    used_transaction_ids.add(id(txn))
    return ValidationResult(
        check_type=CheckType.SALARY_DATE,
        passed=True,
        score=score,
        document_id=slip.doc_id,
        evidence={
            "source_text": slip.salary_month.strftime("%B %Y"),
            "target_text": txn.txn_date.strftime("%Y-%m") if txn.txn_date else None,
            "match_type": "DATE_MATCH",
            "matched_transaction": txn,
        },
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
        evidence={
            "source_text": slip.employer_name,
            "target_text": matched_txn.narration,
            "match_type": "FUZZY",
        },
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
        document_id=bank_statement.doc_id,
        evidence={
            "source_value": total_slips,
            "target_value": matched_slips,
            "match_type": "COUNT_MATCH",
            "stmt_duration": stmt_duration,
            "total_slips": total_slips,
            "confidence_score": confidence_score,
        },
    )


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

    return results
