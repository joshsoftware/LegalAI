"""Request/response schemas for POST /cases.

Mirrors the JSON shape documented in docs/Workflow.md and used by
scripts/sample_case.json — one applicant_ref plus a flat list of documents.
"""

from typing import Any

from pydantic import BaseModel


class SalarySlipIn(BaseModel):
    extracted_fields: dict[str, Any]
    source_file_ref: str | None = None


class DocumentIn(BaseModel):
    doc_type: str
    extracted_fields: dict[str, Any]
    source_file_ref: str | None = None
    salary_slips: list[SalarySlipIn] | None = None  # only present when doc_type == SALARY_SLIP


class CaseCreateRequest(BaseModel):
    applicant_ref: str
    documents: list[DocumentIn]


class ValidationResultOut(BaseModel):
    check_type: str
    passed: bool
    score: float
    document_id: str | None = None
    evidence: dict[str, Any] | None = None


class CaseCreateResponse(BaseModel):
    case_id: str
    applicant_ref: str
    decision: str
    overall_score: float
    reasons: list[str]
    validation_results: list[ValidationResultOut]
