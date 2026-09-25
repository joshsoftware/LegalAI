"""Tests for compute_score's weighting and renormalization contract.

These pin down behaviour that is easy to break silently: the weighted
average looks like three lines of obvious arithmetic, but it decides
whether a case passes, and a mistyped weight key would not raise -- it
would just quietly move every score.
"""

import pytest

from app.services import validation_config as cfg
from app.services.dto import CheckType, ValidationResult
from app.services.scoring import compute_score


def _result(check_type, score):
    return ValidationResult(check_type=check_type, passed=score >= 50, score=score)


def test_empty_results_score_zero():
    result = compute_score([])

    assert result.overall_score == 0.0
    assert result.component_scores == {}


def test_same_check_type_is_averaged_before_weighting():
    """Four NAME results (one per document) collapse to one component."""
    result = compute_score(
        [_result(CheckType.NAME, s) for s in (100.0, 100.0, 50.0, 50.0)]
    )

    assert result.component_scores["NAME"] == 75.0


def test_score_renormalizes_over_observed_check_types_only():
    """A case that produced only NAME results scores on NAME alone, rather
    than being diluted toward zero by check types that never ran."""
    result = compute_score([_result(CheckType.NAME, 80.0)])

    assert result.overall_score == pytest.approx(80.0)


def test_absent_optional_check_type_does_not_change_the_score():
    """The reason SALARY_CONTINUITY's weight was not carved out of another
    check's: a case with no gap months must score exactly as it would have
    before that check type existed."""
    without = compute_score(
        [_result(CheckType.NAME, 90.0), _result(CheckType.SALARY_CREDIT_COUNT, 60.0)]
    )
    with_continuity = compute_score(
        [
            _result(CheckType.NAME, 90.0),
            _result(CheckType.SALARY_CREDIT_COUNT, 60.0),
            _result(CheckType.SALARY_CONTINUITY, 100.0),
        ]
    )

    expected = (0.15 * 90.0 + 0.25 * 60.0) / (0.15 + 0.25)
    assert without.overall_score == pytest.approx(expected)
    assert with_continuity.overall_score > without.overall_score


def test_unweighted_check_types_are_reported_but_not_scored():
    """SALARY_DATE, AADHAAR and PAN appear in component_scores for display
    and audit, but must not move overall_score -- SALARY_DATE because it
    gates other checks rather than scoring, AADHAAR/PAN because they are
    only emitted by the mandatory-presence check."""
    scored_only = compute_score([_result(CheckType.NAME, 90.0)])
    with_unweighted = compute_score(
        [
            _result(CheckType.NAME, 90.0),
            _result(CheckType.SALARY_DATE, 0.0),
            _result(CheckType.AADHAAR, 0.0),
            _result(CheckType.PAN, 0.0),
        ]
    )

    assert with_unweighted.overall_score == pytest.approx(scored_only.overall_score)
    assert set(with_unweighted.component_scores) == {"NAME", "SALARY_DATE", "AADHAAR", "PAN"}


def test_only_falsifiable_check_types_carry_weight():
    """Guards the core invariant: a check type may only carry weight if two
    documents can genuinely disagree about it. ADDRESS, AADHAAR and PAN each
    have a single source document that the Golden Record copies verbatim, so
    comparing them to it compares a value with itself and cannot fail."""
    assert set(cfg.VALIDATION_WEIGHTS) == {
        "NAME",
        "DOB",
        "EMPLOYER",
        "SALARY_CREDIT_COUNT",
        "SALARY_CONTINUITY",
    }
