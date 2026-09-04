from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.case import CaseCreateRequest, CaseCreateResponse, ValidationResultOut
from app.services.case_parsing import CaseParseError, parse_case
from app.services.persistence import save_pipeline_result
from app.services.pipeline import run_pipeline
from app.utils.json_safe import json_safe

router = APIRouter(tags=["cases"])


def _format_parse_errors(exc: CaseParseError) -> dict:
    """Build the 400 body listing every field that failed to parse.

    Everything here must be JSON-native: FastAPI's HTTPException handler does
    a bare `JSONResponse({"detail": exc.detail})` with no jsonable_encoder,
    so a dataclass or date left in `detail` would blow up at render time and
    surface as a 500 instead of this 400.
    """
    return {
        "error": "invalid_field_format",
        "message": f"{len(exc.errors)} field value(s) could not be parsed.",
        "fields": [
            {
                "document": err.document,
                "field": err.field,
                "value": err.value,
                "expected": err.expected,
                "reason": err.reason,
            }
            for err in exc.errors
        ],
    }


@router.post("/cases", response_model=CaseCreateResponse)
async def create_case(
    request: CaseCreateRequest, db: AsyncSession = Depends(get_db)
) -> CaseCreateResponse:
    try:
        case_input = parse_case(request.model_dump())
    except CaseParseError as exc:
        raise HTTPException(status_code=400, detail=_format_parse_errors(exc)) from exc
    except ValueError as exc:
        # Backstop for structural problems that aren't per-field format
        # failures; keeps the legacy string `detail` shape.
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
