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
    """Shift a date by whole calendar months, landing on the first of the month.

    Args:
        d (date): The starting date. Only its year and month are used.
        months (int): How many months to move forward (negative moves back).

    Returns:
        date: The first day of the resulting month.
    """
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _month_window(salary_month: date) -> tuple[date, date]:
    """Build the date range in which a slip's salary credit may appear.

    Payroll dates vary by employer (paid on the 1st, or late into the next
    month), so the range starts SALARY_CREDIT_BUFFER_DAYS before the salary
    month and ends with the month SALARY_CREDIT_EXTRA_MONTHS later. E.g. for
    a March slip with buffer=5, extra=1: Feb 24 -> Apr 30.

    Args:
        salary_month (date): The month the slip is for. The day is ignored.

    Returns:
        tuple[date, date]: The (start, end) dates of the window, inclusive.
    """
    window_start = date(salary_month.year, salary_month.month, 1) - timedelta(
        days=cfg.SALARY_CREDIT_BUFFER_DAYS
    )
    window_end_month = _add_months(salary_month, cfg.SALARY_CREDIT_EXTRA_MONTHS)
    last_day = monthrange(window_end_month.year, window_end_month.month)[1]
    window_end = date(window_end_month.year, window_end_month.month, last_day)
    return window_start, window_end


def _split_into_months(start: date, end: date) -> list[date]:
    """List every calendar month touched by a date range.

    Args:
        start (date): First day of the range.
        end (date): Last day of the range, inclusive.

    Returns:
        list[date]: First-of-month dates in chronological order, including
            partial months at both ends. Empty if start is after end.
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
    """Check whether an amount is within SALARY_AMOUNT_TOLERANCE_PCT of the expected one.

    Args:
        amount (float): The bank transaction amount.
        expected (float): The net salary declared on the slip.

    Returns:
        bool: True if the percentage difference is within tolerance. Always
            False when expected is zero, since no percentage can be computed.
    """
    if not expected:
        return False
    pct_diff = abs(amount - expected) / expected * 100.0
    return pct_diff <= cfg.SALARY_AMOUNT_TOLERANCE_PCT


def _candidate_transactions(
    window: tuple[date, date], transactions: list[BankTransaction], expected_amount: float | None
) -> list[BankTransaction]:
    """Filter bank transactions down to those that could be this slip's salary credit.

    The amount gate runs before narration similarity gets a vote, so a
    same-employer bonus or reimbursement with a different amount can never
    mask a genuinely missing salary credit.

    Args:
        window (tuple[date, date]): Inclusive (start, end) dates, from _month_window.
        transactions (list[BankTransaction]): Every transaction on the statement.
        expected_amount (float or None): The slip's declared net salary. When
            None, the amount gate is skipped.

    Returns:
        list[BankTransaction]: Positive (credit) transactions dated inside
            the window and within amount tolerance.
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
    """Score how close an amount is to the expected one.

    Args:
        amount (float): The bank transaction amount.
        expected (float): The net salary declared on the slip.

    Returns:
        float: 100.0 for an exact match, falling linearly with the relative
            difference, clamped to 0.0-100.0. 0.0 when expected is zero.
    """
    if not expected:
        return 0.0
    closeness = 100.0 * (1 - abs(amount - expected) / expected)
    return max(0.0, min(100.0, closeness))


def _score_transaction(txn: BankTransaction, employer_name: str, expected_amount: float) -> float:
    """Score how likely a transaction is to be the slip's salary credit.

    Args:
        txn (BankTransaction): The candidate transaction.
        employer_name (str): Employer declared on the slip, matched against
            the narration. An empty name scores 0 on that part.
        expected_amount (float): The slip's declared net salary.

    Returns:
        float: Weighted blend (0-100) of employer similarity and amount
            closeness, using the TXN_SELECTION_*_WEIGHT settings.
    """
    employer_score = employer_similarity(employer_name, txn.narration) if employer_name else 0.0
    amount_score = _amount_closeness(txn.amount, expected_amount)
    return (
        cfg.TXN_SELECTION_EMPLOYER_WEIGHT * employer_score
        + cfg.TXN_SELECTION_AMOUNT_WEIGHT * amount_score
    )


def _select_best_transaction(
    candidates: list[BankTransaction], employer_name: str | None, expected_amount: float | None
) -> tuple[BankTransaction, float] | None:
    """Pick the highest-scoring candidate, if it scores well enough.

    Args:
        candidates (list[BankTransaction]): Transactions that passed
            _candidate_transactions.
        employer_name (str or None): Employer declared on the slip.
        expected_amount (float or None): The slip's declared net salary.

    Returns:
        tuple[BankTransaction, float] or None: The best transaction and its
            score, or None if there are no candidates, no expected amount, or
            the best score is below TXN_SELECTION_MIN_SCORE.
    """
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
    """Match one slip to its salary credit on the bank statement.

    Overlapping month windows mean one credit could otherwise count as
    evidence for two different months of income, so claimed credits are
    tracked and skipped.

    Args:
        slip (SalarySlipDoc): The slip to verify.
        bank_statement (BankStatementDoc): The statement to search.
        used_transaction_ids (set[int]): id() of every transaction already
            claimed by an earlier slip. Updated in place when this slip
            claims one.

    Returns:
        ValidationResult: A SALARY_DATE result. On success its evidence holds
            "matched_transaction"; on failure the reason is missing_salary_month,
            missing_net_salary or no_matching_credit_in_window.
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
    """Check a slip's employer against the narration of its own matched credit.

    Never compared against another month's slip: switching jobs mid-history
    is legitimate, so each month stands on its own evidence.

    Args:
        slip (SalarySlipDoc): The slip whose employer to verify.
        slip_result (ValidationResult): That slip's SALARY_DATE result from
            _validate_salary_slip.

    Returns:
        ValidationResult: An EMPLOYER result scored by employer similarity.
            Fails if the slip has no employer, has no matched credit, or
            scores below EMPLOYER_MATCH_THRESHOLD.
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
    """Summarise how many slips found a matching salary credit.

    Args:
        salary_slips (list[SalarySlipDoc]): All slips in the case.
        bank_statement (BankStatementDoc): The statement, used for its date span.
        slip_results (list[ValidationResult]): Each slip's SALARY_DATE result.

    Returns:
        ValidationResult: A SALARY_CREDIT_COUNT result scored as the percentage
            of slips matched. Passes only when every slip matched.
    """
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
    """Return the calendar months a bank statement covers.

    A trailing partial month is excluded: the statement was pulled part-way
    through it, so that month's slip has not been issued yet and reporting it
    as missing would penalise an applicant for a document that cannot exist.

    Args:
        bank_statement (BankStatementDoc): The statement whose transaction
            dates define the covered period.

    Returns:
        list[date]: First-of-month dates in chronological order, or an empty
            list if no transaction carries a date.
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
    """Return the months the applicant actually submitted a salary slip for.

    Args:
        salary_slips (list[SalarySlipDoc]): The slips submitted with the case.

    Returns:
        set[date]: First-of-month dates of every slip that has a
            salary_month. Undated slips cover nothing.
    """
    return {slip.salary_month for slip in salary_slips if slip.salary_month is not None}


def _missing_slip_checks(
    salary_slips: list[SalarySlipDoc], bank_statement: BankStatementDoc
) -> list[ValidationResult]:
    """Report every statement month that has no submitted salary slip.

    Args:
        salary_slips (list[SalarySlipDoc]): The slips submitted with the case.
        bank_statement (BankStatementDoc): The statement whose covered months
            the slips are checked against.

    Returns:
        list[ValidationResult]: One failed SALARY_CONTINUITY result (score
            0.0, no document_id) per uncovered month, with the month in
            evidence["month"]. Empty when every month has a slip.
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
    """Run every salary and employer check for a case.

    Slips claim credits in chronological order, so the earliest month gets
    first pick of a credit that falls in two overlapping windows.

    Args:
        case (CaseInput): The parsed case.

    Returns:
        list[ValidationResult]: SALARY_DATE and EMPLOYER results per slip, one
            SALARY_CREDIT_COUNT result, and a SALARY_CONTINUITY result per
            month missing a slip. Empty if the case has no slips or no
            bank statement.
    """
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
