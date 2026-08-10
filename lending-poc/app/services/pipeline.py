"""Orchestrates Golden Record -> Identity -> Business -> Scoring ->
Decision in one call, with a simple in-memory audit log.
"""

from app.services import business_validation, decision_engine, golden_record, scoring
from app.services import validation_config as cfg
from app.services.dto import CaseInput, Decision, DecisionResult, PipelineResult
from app.services.identity_validation import run_identity_validation


def run_pipeline(case: CaseInput) -> PipelineResult:
    audit_log: list[str] = []
    audit_log.append(f"INGEST: case_created applicant_ref={case.applicant_ref}")

    present = case.present_doc_types()
    missing = set(cfg.REQUIRED_DOCUMENT_TYPES) - present
    if missing:
        reasons = [f"MISSING_DOCUMENT:{doc_type}" for doc_type in sorted(missing)]
        audit_log.append(f"PIPELINE: precheck_failed missing={sorted(missing)}")
        decision_result = DecisionResult(decision=Decision.FAIL, reasons=reasons, overall_score=0.0)
        return PipelineResult(
            golden_record=None,
            validation_results=[],
            score_result=None,
            decision_result=decision_result,
            audit_log=audit_log,
        )

    golden = golden_record.build_golden_record(case)
    audit_log.append(
        f"GOLDEN_RECORD: built name={golden.name!r} address={golden.address!r}"
    )

    identity_results = run_identity_validation(case, golden)
    audit_log.append(f"IDENTITY_VALIDATION: {len(identity_results)} checks run")

    business_results = business_validation.run_business_validation(case)
    audit_log.append(f"BUSINESS_VALIDATION: {len(business_results)} checks run")

    all_results = identity_results + business_results

    score_result = scoring.compute_score(all_results)
    audit_log.append(f"SCORING: overall_score={score_result.overall_score:.2f}")

    decision_result = decision_engine.make_decision(score_result, all_results)
    audit_log.append(
        f"DECISION: {decision_result.decision.value} reasons={decision_result.reasons}"
    )

    return PipelineResult(
        golden_record=golden,
        validation_results=all_results,
        score_result=score_result,
        decision_result=decision_result,
        audit_log=audit_log,
    )
