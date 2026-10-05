"""Tests for make_decision's PASS / NEEDS_REVIEW / FAIL rules."""

from app.services.decision_engine import make_decision
from app.services.dto import CheckType, Decision, ScoreResult, ValidationResult


def _result(check_type, score, passed=True, failure_reason=None):
    return ValidationResult(
        check_type=check_type, passed=passed, score=score, failure_reason=failure_reason
    )


def _score(overall):
    return ScoreResult(overall_score=overall, component_scores={})


def test_high_score_with_all_checks_passing_is_pass():
    results = [_result(CheckType.NAME, 100.0), _result(CheckType.DOB, 100.0)]

    assert make_decision(_score(97.0), results).decision == Decision.PASS


def test_failed_name_check_blocks_pass_even_with_high_score():
    """The real case: PAN-vs-Aadhaar name fails (66.7) but averages with two
    100s into a NAME mean of 88.9, giving an overall 97.2."""
    results = [
        _result(CheckType.NAME, 66.7, passed=False, failure_reason="name_below_threshold"),
        _result(CheckType.NAME, 100.0),
        _result(CheckType.NAME, 100.0),
        _result(CheckType.DOB, 100.0),
    ]

    decision = make_decision(_score(97.2), results)

    assert decision.decision == Decision.NEEDS_REVIEW
    assert decision.reasons == ["NAME:name_below_threshold"]


def test_failed_dob_check_blocks_pass_even_with_high_score():
    results = [
        _result(CheckType.NAME, 100.0),
        _result(CheckType.DOB, 0.0, passed=False, failure_reason="dob_differs"),
    ]

    decision = make_decision(_score(95.0), results)

    assert decision.decision == Decision.NEEDS_REVIEW
    assert decision.reasons == ["DOB:dob_differs"]


def test_failed_non_identity_check_does_not_block_pass():
    """Only NAME and DOB are gated; e.g. one weak employer match can still pass."""
    results = [
        _result(CheckType.NAME, 100.0),
        _result(
            CheckType.EMPLOYER, 70.0, passed=False, failure_reason="employer_narration_mismatch"
        ),
    ]

    assert make_decision(_score(92.0), results).decision == Decision.PASS


def test_low_score_with_failed_name_is_still_fail():
    results = [_result(CheckType.NAME, 20.0, passed=False, failure_reason="name_below_threshold")]

    assert make_decision(_score(40.0), results).decision == Decision.FAIL
