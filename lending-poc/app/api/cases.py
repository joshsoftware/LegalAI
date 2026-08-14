from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.case import CaseCreateRequest, CaseCreateResponse, ValidationResultOut
from app.services.case_parsing import parse_case
from app.services.persistence import save_pipeline_result
from app.services.pipeline import run_pipeline
from app.utils.json_safe import json_safe

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseCreateResponse)
async def create_case(
    request: CaseCreateRequest, db: AsyncSession = Depends(get_db)
) -> CaseCreateResponse:
    try:
        case_input = parse_case(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pipeline_result = run_pipeline(case_input)
    case = await save_pipeline_result(db, case_input, pipeline_result)

    return CaseCreateResponse(
        case_id=str(case.id),
        applicant_ref=case_input.applicant_ref,
        decision=pipeline_result.decision_result.decision.value,
        overall_score=pipeline_result.decision_result.overall_score,
        reasons=pipeline_result.decision_result.reasons,
        validation_results=[
            ValidationResultOut(
                check_type=r.check_type.value,
                passed=r.passed,
                score=r.score,
                document_id=r.document_id,
                evidence=json_safe(r.evidence) if r.evidence else None,
            )
            for r in pipeline_result.validation_results
        ],
    )
