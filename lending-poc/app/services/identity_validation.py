"""Checks every document agrees with the Golden Record on name and DOB.
Also enforces that mandatory identity fields exist on the Golden Record at
all, regardless of why they're missing.

Only NAME and DOB are *compared*, because a comparison is only meaningful
when its two sides have independent provenance. Name appears on all four
documents; DOB appears on both AADHAAR and PAN. Those two can genuinely
disagree, so scoring them means something.

ADDRESS, AADHAAR number and PAN number are deliberately NOT compared. Each
has exactly one source document, and build_golden_record copies that value
verbatim -- so comparing a document's value back against the Golden Record
compared a value with itself and always scored 100 (or 50, for an Aadhaar
too heavily masked to read 4 digits from; never a mismatch). A check that
cannot fail isn't a check -- worse, since compute_score renormalizes by
observed weight, guaranteed-100 components pulled borderline cases up
toward the pass threshold. Together these three accounted for 0.40 of the
weight table, all of it padding.

All three values are still resolved onto the Golden Record and still
required to be *present* -- see check_mandatory_presence, which remains the
trigger for the hard-FAIL path in decision_engine. "Does this applicant
have a PAN at all?" is a real question; "does the PAN match itself?" is not.

The same rule applies one level down, inside the checks that DO survive: a
document is never compared against a value it supplied itself, tracked via
`golden.<field>_source`. See validate_document_against_golden.
"""

from app.matching import exact, fuzzy
from app.services import validation_config as cfg
from app.services.dto import CaseInput, CheckType, GoldenRecord, ValidationResult

MANDATORY_GOLDEN_FIELDS = {
    CheckType.NAME: "name",
    CheckType.AADHAAR: "aadhaar_number",
    CheckType.PAN: "pan_number",
    CheckType.DOB: "date_of_birth",
}


def check_mandatory_presence(golden: GoldenRecord) -> list[ValidationResult]:
    '''Checks that the Golden Record itself has a name, Aadhaar number, PAN number, and DOB'''
    
    results = []
    for check_type, field_name in MANDATORY_GOLDEN_FIELDS.items():
        if getattr(golden, field_name) is None:
            results.append(
                ValidationResult(
                    check_type=check_type,
                    passed=False,
                    score=0.0,
                    failure_reason="missing_in_golden_record",
                )
            )
    return results


def _exact_result_to_validation(check_type: CheckType, outcome, document_id: str) -> ValidationResult:
    passed = outcome.result == exact.MatchResult.MATCH
    score = 100.0 if passed else (50.0 if outcome.result == exact.MatchResult.INCONCLUSIVE else 0.0)
    return ValidationResult(
        check_type=check_type,
        passed=passed,
        score=score,
        document_id=document_id,
        failure_reason=None if passed else outcome.reason,
    )


def validate_document_against_golden(
    document_id: str,
    doc_name: str | None,
    doc_dob,
    golden: GoldenRecord,
) -> list[ValidationResult]:
    """Compares one document's identity fields against the Golden Record.

    Only NAME and DOB are compared, because they are the only identity
    fields more than one document carries. Aadhaar and PAN numbers each
    have exactly one source document, and build_golden_record copies that
    value verbatim -- see this module's docstring.

    A document is never compared against a Golden Record field it supplied
    itself. `golden.<field>_source` records where each value came from, and
    for that document the comparison would read a value against its own
    copy: a guaranteed 100 that dilutes whatever genuine disagreement the
    *other* documents report. Concretely, with the DOB sourced from AADHAAR,
    a PAN that contradicts it outright used to average 100 and 0 into a
    component score of 50 -- half the signal, purely from the self-match.

    A field whose only source is the document that supplied it therefore
    produces no result at all rather than a free 100. That is the honest
    outcome -- the value is present but uncorroborated -- and compute_score
    handles it correctly, since it renormalizes over the check types
    actually observed rather than assuming a fixed set.
    """
    results = []

    if doc_name is not None and golden.name is not None and document_id != golden.name_source:
        score = fuzzy.name_similarity(golden.name, doc_name)
        passed = score >= cfg.NAME_MATCH_THRESHOLD
        results.append(
            ValidationResult(
                check_type=CheckType.NAME,
                passed=passed,
                score=score,
                document_id=document_id,
                failure_reason=None if passed else "name_below_threshold",
            )
        )

    if doc_dob is not None and document_id != golden.dob_source:
        outcome = exact.dob_match(golden.date_of_birth, doc_dob)
        results.append(_exact_result_to_validation(CheckType.DOB, outcome, document_id))

    return results


def run_identity_validation(case: CaseInput, golden: GoldenRecord) -> list[ValidationResult]:
    # Stage 3: does every document agree with the Golden Record?
    # 1) check_mandatory_presence: Golden Record itself must have name/Aadhaar/PAN/DOB,
    #    else that check type is an automatic hard failure (score 0.0).
    # 2) For each present document, validate_document_against_golden compares its fields
    #    against the Golden Record (fuzzy name, exact DOB).
    # All ValidationResults (pass/fail + score + reason) are flattened into one list.
    
    results: list[ValidationResult] = []
    results.extend(check_mandatory_presence(golden))

    if case.aadhaar:
        results.extend(
            validate_document_against_golden(
                document_id=case.aadhaar.doc_id,
                doc_name=case.aadhaar.name,
                doc_dob=case.aadhaar.date_of_birth,
                golden=golden,
            )
        )

    if case.pan:
        results.extend(
            validate_document_against_golden(
                document_id=case.pan.doc_id,
                doc_name=case.pan.name,
                doc_dob=case.pan.date_of_birth,
                golden=golden,
            )
        )

    for slip in case.salary_slips:
        results.extend(
            validate_document_against_golden(
                document_id=slip.doc_id,
                doc_name=slip.name,
                doc_dob=None,
                golden=golden,
            )
        )

    if case.bank_statement:
        results.extend(
            validate_document_against_golden(
                document_id=case.bank_statement.doc_id,
                doc_name=case.bank_statement.name,
                doc_dob=None,
                golden=golden,
            )
        )

    return results
