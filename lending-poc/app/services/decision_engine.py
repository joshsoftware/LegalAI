"""Final PASS / FAIL / NEEDS_REVIEW logic."""

from app.services import validation_config as cfg
from app.services.dto import CheckType, Decision, DecisionResult, ScoreResult, ValidationResult

MANDATORY_CHECK_TYPES = {CheckType.NAME, CheckType.AADHAAR, CheckType.PAN, CheckType.DOB}

# Identity comparisons that must all agree before a case can PASS. The score
# averages every NAME result into one number, so one documents-disagree
# failure (e.g. PAN vs Aadhaar) gets diluted by the matching ones and can
# still land above the pass threshold.
IDENTITY_MISMATCH_CHECK_TYPES = {CheckType.NAME, CheckType.DOB}


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

    identity_mismatches = [
        r for r in validation_results if r.check_type in IDENTITY_MISMATCH_CHECK_TYPES and not r.passed
    ]

    # A high score alone isn't enough to PASS when an identity check failed.
    # Falling through is safe: a score this high can't hit the FAIL branch
    # below, so it lands in NEEDS_REVIEW.
    if score.overall_score >= cfg.DECISION_PASS_THRESHOLD and not identity_mismatches:
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
