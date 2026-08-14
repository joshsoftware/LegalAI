"""Persists one pipeline run (CaseInput + PipelineResult) to the database.

The in-memory dataclasses in app.services.dto reference documents by their
string doc_id (e.g. "AADHAAR", "SALARY_SLIP-0"). This module inserts the
Document rows first and keeps a doc_id -> Document.id map so
ValidationResult.document_id (also a doc_id string) can be resolved to the
real foreign key.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dto import CaseInput, Decision, DocType
from app.services.dto import PipelineResult as PipelineResultDTO
from app.utils.json_safe import json_safe
from db.models.case import Case, CaseStatus
from db.models.document import Document
from db.models.golden_record import GoldenRecord as GoldenRecordModel
from db.models.pipeline_result import PipelineResult as PipelineResultModel
from db.models.validation_result import ValidationResult as ValidationResultModel

_DECISION_TO_CASE_STATUS = {
    Decision.PASS: CaseStatus.PASS,
    Decision.FAIL: CaseStatus.FAIL,
    Decision.NEEDS_REVIEW: CaseStatus.NEEDS_REVIEW,
}


def _mask_pan(pan: str | None) -> str | None:
    """Mask all but the last 4 characters of a PAN for JSONB storage.

    The full value is encrypted in the GoldenRecord; the document payload
    only needs enough for audit trail without exposing the raw PAN.
    """
    if not pan:
        return pan
    visible = min(4, len(pan))
    return "X" * (len(pan) - visible) + pan[-visible:]


def _document_rows(case: CaseInput) -> list[tuple[str, Document]]:
    """Returns (doc_id, Document) pairs for every document present on the case."""
    rows: list[tuple[str, Document]] = []

    if case.aadhaar:
        rows.append((
            case.aadhaar.doc_id,
            Document(
                doc_type=DocType.AADHAAR,
                source_file_ref=case.aadhaar.source_file_ref,
                extracted_fields={
                    "name": case.aadhaar.name,
                    "address": case.aadhaar.address,
                    "aadhaar_number": case.aadhaar.aadhaar_number,
                    "date_of_birth": case.aadhaar.date_of_birth.isoformat() if case.aadhaar.date_of_birth else None,
                },
            ),
        ))

    if case.pan:
        rows.append((
            case.pan.doc_id,
            Document(
                doc_type=DocType.PAN,
                source_file_ref=case.pan.source_file_ref,
                extracted_fields={"name": case.pan.name, "pan_number": _mask_pan(case.pan.pan_number)},
            ),
        ))

    if case.address_proof:
        rows.append((
            case.address_proof.doc_id,
            Document(
                doc_type=DocType.ADDRESS_PROOF,
                source_file_ref=case.address_proof.source_file_ref,
                extracted_fields={"address": case.address_proof.address},
            ),
        ))

    for slip in case.salary_slips:
        rows.append((
            slip.doc_id,
            Document(
                doc_type=DocType.SALARY_SLIP,
                source_file_ref=slip.source_file_ref,
                extracted_fields={
                    "name": slip.name,
                    "employer_name": slip.employer_name,
                    "net_salary": slip.net_salary,
                    "salary_month": slip.salary_month.isoformat() if slip.salary_month else None,
                },
            ),
        ))

    if case.bank_statement:
        rows.append((
            case.bank_statement.doc_id,
            Document(
                doc_type=DocType.BANK_STATEMENT,
                source_file_ref=case.bank_statement.source_file_ref,
                extracted_fields={
                    "name": case.bank_statement.name,
                    "transactions": [
                        {
                            "narration": txn.narration,
                            "amount": txn.amount,
                            "date": txn.txn_date.isoformat() if txn.txn_date else None,
                        }
                        for txn in case.bank_statement.transactions
                    ],
                },
            ),
        ))

    return rows


async def save_pipeline_result(
    db: AsyncSession, case_input: CaseInput, pipeline_result: PipelineResultDTO
) -> Case:
    """Persists one pipeline run in a single transaction and returns the Case row.

    Caller owns the commit (via app.database.get_db, which commits on
    success / rolls back on error).
    """
    case = Case(
        applicant_ref=case_input.applicant_ref,
        status=_DECISION_TO_CASE_STATUS[pipeline_result.decision_result.decision],
    )
    db.add(case)
    await db.flush()  # assigns case.id

    doc_id_to_pk: dict[str, uuid.UUID] = {}
    for doc_id, document in _document_rows(case_input):
        document.case_id = case.id
        db.add(document)
        await db.flush()  # assigns document.id
        doc_id_to_pk[doc_id] = document.id

    golden = pipeline_result.golden_record
    if golden is not None:
        db.add(
            GoldenRecordModel(
                case_id=case.id,
                name=golden.name,
                address=golden.address,
                address_embedding=golden.address_embedding or None,
                aadhaar_number=golden.aadhaar_number,
                pan_number=golden.pan_number,
                date_of_birth=golden.date_of_birth,
            )
        )

    for result in pipeline_result.validation_results:
        db.add(
            ValidationResultModel(
                case_id=case.id,
                document_id=doc_id_to_pk.get(result.document_id) if result.document_id else None,
                check_type=result.check_type,
                passed=result.passed,
                score=result.score,
                evidence=json_safe(result.evidence) if result.evidence else None,
            )
        )

    score_result = pipeline_result.score_result
    db.add(
        PipelineResultModel(
            case_id=case.id,
            overall_score=score_result.overall_score if score_result else 0.0,
            decision=pipeline_result.decision_result.decision,
            reasons=pipeline_result.decision_result.reasons,
        )
    )

    await db.flush()
    return case
