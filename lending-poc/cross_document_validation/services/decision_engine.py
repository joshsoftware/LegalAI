"""Final PASS / FAIL / NEEDS_REVIEW logic."""

from cross_document_validation.services import validation_config as cfg
from cross_document_validation.services.dto import CheckType, Decision, DecisionResult, ScoreResult, ValidationResult

MANDATORY_CHECK_TYPES = {CheckType.NAME, CheckType.AADHAAR, CheckType.PAN, CheckType.DOB}


def make_decision(
    score: ScoreResult, validation_results: list[ValidationResult]
) -> DecisionResult:
    reasons: list[str] = []

    mandatory_failures = [
        r
        for r in validation_results
        if r.check_type in MANDATORY_CHECK_TYPES
        and not r.passed
        and r.failure_reason == "missing_in_golden_record"
    ]
    if mandatory_failures:
        reasons = [f"MANDATORY_FIELD_MISSING:{r.check_type.value}" for r in mandatory_failures]
        return DecisionResult(
            decision=Decision.FAIL, reasons=reasons, overall_score=score.overall_score
        )

    if score.overall_score >= cfg.DECISION_PASS_THRESHOLD:
        return DecisionResult(decision=Decision.PASS, reasons=["score_meets_pass_threshold"], overall_score=score.overall_score)

    if score.overall_score < cfg.DECISION_FAIL_THRESHOLD:
        return DecisionResult(
            decision=Decision.FAIL,
            reasons=["score_below_fail_threshold"],
            overall_score=score.overall_score,
        )

    failing_checks = [
        f"{r.check_type.value}:{r.failure_reason or 'below_threshold'}"
        for r in validation_results
        if not r.passed
    ]
    return DecisionResult(
        decision=Decision.NEEDS_REVIEW,
        reasons=failing_checks or ["score_in_review_band"],
        overall_score=score.overall_score,
    )
