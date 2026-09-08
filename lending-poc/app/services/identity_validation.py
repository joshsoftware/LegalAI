"""Checks every document agrees with the Golden Record: name, Aadhaar,
PAN, DOB. Also enforces that mandatory identity fields exist on the
Golden Record at all, regardless of why they're missing.

Address is deliberately NOT checked here. golden.address is copied verbatim
from AADHAAR -- the only document that carries an address -- so comparing a
document's address back against the Golden Record compared a value with
itself and always scored 100. A check that cannot fail isn't a check --
worse, since compute_score renormalizes by observed weight, a guaranteed
100 pulled borderline cases up toward the pass threshold. Address is still
resolved and stored on the Golden Record; it is simply not scored.
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
    doc_aadhaar: str | None,
    doc_pan: str | None,
    doc_dob,
    golden: GoldenRecord,
) -> list[ValidationResult]:
    results = []

    if doc_name is not None and golden.name is not None:
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

    if doc_aadhaar is not None:
        outcome = exact.aadhaar_match(golden.aadhaar_number, doc_aadhaar)
        results.append(_exact_result_to_validation(CheckType.AADHAAR, outcome, document_id))

    if doc_pan is not None:
        outcome = exact.pan_match(golden.pan_number, doc_pan)
        results.append(_exact_result_to_validation(CheckType.PAN, outcome, document_id))

    if doc_dob is not None:
        outcome = exact.dob_match(golden.date_of_birth, doc_dob)
        results.append(_exact_result_to_validation(CheckType.DOB, outcome, document_id))

    return results


def run_identity_validation(case: CaseInput, golden: GoldenRecord) -> list[ValidationResult]:
    # Stage 3: does every document agree with the Golden Record?
    # 1) check_mandatory_presence: Golden Record itself must have name/Aadhaar/PAN/DOB,
    #    else that check type is an automatic hard failure (score 0.0).
    # 2) For each present document, validate_document_against_golden compares its fields
    #    against the Golden Record (fuzzy name, exact Aadhaar/PAN/DOB).
    # All ValidationResults (pass/fail + score + reason) are flattened into one list.
    
    results: list[ValidationResult] = []
    results.extend(check_mandatory_presence(golden))

    if case.aadhaar:
        results.extend(
            validate_document_against_golden(
                document_id=case.aadhaar.doc_id,
                doc_name=case.aadhaar.name,
                doc_aadhaar=case.aadhaar.aadhaar_number,
                doc_pan=None,
                doc_dob=case.aadhaar.date_of_birth,
                golden=golden,
            )
        )

    if case.pan:
        results.extend(
            validate_document_against_golden(
                document_id=case.pan.doc_id,
                doc_name=case.pan.name,
                doc_aadhaar=None,
                doc_pan=case.pan.pan_number,
                doc_dob=None,
                golden=golden,
            )
        )

    for slip in case.salary_slips:
        results.extend(
            validate_document_against_golden(
                document_id=slip.doc_id,
                doc_name=slip.name,
                doc_aadhaar=None,
                doc_pan=None,
                doc_dob=None,
                golden=golden,
            )
        )

    if case.bank_statement:
        results.extend(
            validate_document_against_golden(
                document_id=case.bank_statement.doc_id,
                doc_name=case.bank_statement.name,
                doc_aadhaar=None,
                doc_pan=None,
                doc_dob=None,
                golden=golden,
            )
        )

    return results
