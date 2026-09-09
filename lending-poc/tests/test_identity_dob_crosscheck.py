"""Tests that DOB is a *genuine* cross-document check.

Both AADHAAR and PAN print a date of birth, which makes DOB — alongside
name — one of only two identity fields two documents can actually disagree
about. Aadhaar/PAN *numbers* have a single source each, so comparing them
to the Golden Record compares a value with itself; DOB must not degrade
into that same self-comparison.

The regression these tests guard against is a silent one: the PAN DOB used
to be requested from the extractor but dropped before it reached
CaseInput, so the DOB check only ever saw Aadhaar's own value and could
never fail.
"""

from datetime import date

from app.services.dto import AadhaarDoc, CaseInput, CheckType, PanDoc
from app.services.golden_record import build_golden_record
from app.services.identity_validation import run_identity_validation
from app.services.scoring import compute_score


def _case(aadhaar_dob, pan_dob):
    return CaseInput(
        applicant_ref="APP-DOB-0001",
        aadhaar=AadhaarDoc(
            name="Arjun Ramesh Iyer",
            aadhaar_number="644676547841",
            date_of_birth=aadhaar_dob,
        ),
        pan=PanDoc(
            name="Arjun Ramesh Iyer",
            pan_number="AXKPI2938Q",
            date_of_birth=pan_dob,
        ),
    )


def _dob_results(case):
    golden = build_golden_record(case)
    return [r for r in run_identity_validation(case, golden) if r.check_type == CheckType.DOB]


def test_only_the_non_sourcing_document_contributes_a_dob_result():
    """AADHAAR supplied the golden DOB, so comparing it back would score a
    guaranteed 100. Only PAN's value is an actual comparison."""
    results = _dob_results(_case(date(1994, 8, 19), date(1994, 8, 19)))

    assert [r.document_id for r in results] == ["PAN"]
    assert results[0].passed and results[0].score == 100.0


def test_disagreeing_dob_is_caught():
    """The whole point: a PAN DOB that contradicts Aadhaar must fail."""
    results = _dob_results(_case(date(1994, 8, 19), date(1994, 3, 19)))

    pan_result = next(r for r in results if r.document_id == "PAN")
    assert not pan_result.passed
    assert pan_result.score == 0.0
    assert pan_result.failure_reason == "dob_differs"


def test_disagreeing_dob_drives_the_component_to_zero():
    """No self-match is averaged in, so a contradiction is worth the full
    drop rather than being halved to 50 by Aadhaar comparing to itself."""
    agreeing = compute_score(_dob_results(_case(date(1994, 8, 19), date(1994, 8, 19))))
    disagreeing = compute_score(_dob_results(_case(date(1994, 8, 19), date(1994, 3, 19))))

    assert agreeing.component_scores["DOB"] == 100.0
    assert disagreeing.component_scores["DOB"] == 0.0


def test_uncorroborated_dob_produces_no_result_rather_than_a_free_100():
    """With no PAN DOB extracted, Aadhaar's value has nothing to be checked
    against. That must contribute nothing -- compute_score renormalizes over
    observed check types, so an absent DOB is neutral, not a free pass."""
    results = _dob_results(_case(date(1994, 8, 19), None))

    assert results == []


def test_aadhaar_and_pan_numbers_produce_no_comparison_results():
    """Each number has one source document that the Golden Record copies
    verbatim, so a comparison could only ever compare a value with itself.
    Present-and-valid numbers must therefore yield no scored result at all."""
    case = _case(date(1994, 8, 19), date(1994, 8, 19))
    golden = build_golden_record(case)

    results = run_identity_validation(case, golden)
    scored = [r for r in results if r.check_type in (CheckType.AADHAAR, CheckType.PAN)]

    assert scored == []


def test_missing_number_still_hard_fails_via_presence_check():
    """The presence check is the part that carries real signal, and it must
    survive the removal of the value comparison."""
    case = _case(date(1994, 8, 19), date(1994, 8, 19))
    case.pan.pan_number = None
    golden = build_golden_record(case)

    results = run_identity_validation(case, golden)
    pan_result = next(r for r in results if r.check_type == CheckType.PAN)

    assert not pan_result.passed
    assert pan_result.failure_reason == "missing_in_golden_record"


def test_name_skips_whichever_document_sourced_the_golden_name():
    """Same rule as DOB, applied to the field with four sources: the
    document the golden name came from must not self-match."""
    case = _case(date(1994, 8, 19), date(1994, 8, 19))
    golden = build_golden_record(case)

    name_results = [
        r for r in run_identity_validation(case, golden) if r.check_type == CheckType.NAME
    ]

    assert golden.name_source == "AADHAAR"
    assert [r.document_id for r in name_results] == ["PAN"]


def test_dob_source_fallback_flips_which_document_is_compared():
    """With no Aadhaar DOB the golden value comes from PAN, so PAN becomes
    the self-comparison and AADHAAR the genuine one -- the rule follows
    provenance rather than hardcoding a document."""
    case = _case(None, date(1994, 3, 19))
    case.aadhaar.date_of_birth = None
    golden = build_golden_record(case)

    assert golden.dob_source == "PAN"

    # Give Aadhaar a DOB that contradicts the PAN-sourced golden value.
    case.aadhaar.date_of_birth = date(1994, 8, 19)
    results = [r for r in run_identity_validation(case, golden) if r.check_type == CheckType.DOB]

    assert [r.document_id for r in results] == ["AADHAAR"]
    assert not results[0].passed


def test_golden_record_prefers_aadhaar_dob_over_pan():
    golden = build_golden_record(_case(date(1994, 8, 19), date(1994, 3, 19)))

    assert golden.date_of_birth == date(1994, 8, 19)
    assert golden.dob_source == "AADHAAR"


def test_golden_record_falls_back_to_pan_dob():
    """With no Aadhaar DOB, PAN supplies it -- which keeps the mandatory
    presence check satisfied instead of hard-failing the case."""
    golden = build_golden_record(_case(None, date(1994, 3, 19)))

    assert golden.date_of_birth == date(1994, 3, 19)
    assert golden.dob_source == "PAN"
