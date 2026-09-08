"""Request/response schemas for POST /cases.

Mirrors the JSON shape documented in docs/Workflow.md and used by
scripts/sample_case.json — one applicant_ref plus a flat list of documents.

`DocumentIn` is a discriminated union keyed on doc_type: each document kind
gets its own extracted-fields shape, and only SALARY_SLIP carries
salary_slips (and no top-level extracted_fields, matching the documented
sample).
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class BankTransactionIn(BaseModel):
    narration: str | None = None
    # Widened to accept strings for the same reason as net_salary below: the
    # values come from an LLM reading a document, so "75,000" and "Rs. 75,000"
    # are normal. Rejecting them here would 422 before parse_case could
    # normalize them.
    amount: float | str | None = None
    date: str | None = None


class AadhaarFieldsIn(BaseModel):
    name: str | None = None
    address: str | None = None
    # An Aadhaar number is all digits, so an LLM may well emit it unquoted.
    # Pydantic v2 does not coerce int -> str, so without `int` here that
    # 422s; parse_case stringifies it.
    aadhaar_number: str | int | None = None
    date_of_birth: str | None = None


class PanFieldsIn(BaseModel):
    name: str | None = None
    pan_number: str | None = None


class SalarySlipFieldsIn(BaseModel):
    name: str | None = None
    employer_name: str | None = None
    net_salary: float | str | None = None
    salary_month: str | None = None


class BankStatementFieldsIn(BaseModel):
    name: str | None = None
    transactions: list[BankTransactionIn] = Field(default_factory=list)


class SalarySlipIn(BaseModel):
    extracted_fields: SalarySlipFieldsIn
    source_file_ref: str | None = None


class AadhaarDocumentIn(BaseModel):
    doc_type: Literal["AADHAAR"]
    extracted_fields: AadhaarFieldsIn
    source_file_ref: str | None = None


class PanDocumentIn(BaseModel):
    doc_type: Literal["PAN"]
    extracted_fields: PanFieldsIn
    source_file_ref: str | None = None


class SalarySlipDocumentIn(BaseModel):
    doc_type: Literal["SALARY_SLIP"]
    salary_slips: list[SalarySlipIn]
    source_file_ref: str | None = None


class BankStatementDocumentIn(BaseModel):
    doc_type: Literal["BANK_STATEMENT"]
    extracted_fields: BankStatementFieldsIn
    source_file_ref: str | None = None


DocumentIn = Annotated[
    Union[
        AadhaarDocumentIn,
        PanDocumentIn,
        SalarySlipDocumentIn,
        BankStatementDocumentIn,
    ],
    Field(discriminator="doc_type"),
]


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
