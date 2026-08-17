"""Parses the raw request JSON shape (see docs/Workflow.md) into CaseInput.

Used by the POST /cases endpoint.
"""

from datetime import date, datetime

from cross_document_validation.services.dto import (
    AadhaarDoc,
    AddressProofDoc,
    BankStatementDoc,
    BankTransaction,
    CaseInput,
    PanDoc,
    SalarySlipDoc,
)


def _get(fields: dict, key: str) -> str | None:
    """Null-safe field lookup: a missing key, JSON null, and an empty/
    whitespace-only string are all treated as no value."""
    value = fields.get(key)
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_month(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def _parse_float(value) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return float(value)


def parse_case(payload: dict) -> CaseInput:
    case = CaseInput(applicant_ref=payload["applicant_ref"])

    for doc in payload["documents"]:
        doc_type = doc["doc_type"]

        if doc_type == "AADHAAR":
            fields = doc["extracted_fields"]
            case.aadhaar = AadhaarDoc(
                name=_get(fields, "name"),
                address=_get(fields, "address"),
                aadhaar_number=_get(fields, "aadhaar_number"),
                date_of_birth=_parse_date(_get(fields, "date_of_birth")),
                source_file_ref=doc.get("source_file_ref"),
            )

        elif doc_type == "PAN":
            fields = doc["extracted_fields"]
            case.pan = PanDoc(
                name=_get(fields, "name"),
                pan_number=_get(fields, "pan_number"),
                source_file_ref=doc.get("source_file_ref"),
            )

        elif doc_type == "ADDRESS_PROOF":
            fields = doc["extracted_fields"]
            case.address_proof = AddressProofDoc(
                address=_get(fields, "address"),
                source_file_ref=doc.get("source_file_ref"),
            )

        elif doc_type == "SALARY_SLIP":
            slips = doc.get("salary_slips") or []
            if not slips:
                raise ValueError("SALARY_SLIP document must include at least one entry in salary_slips")
            for i, slip in enumerate(slips):
                fields = slip["extracted_fields"]
                case.salary_slips.append(
                    SalarySlipDoc(
                        employer_name=_get(fields, "employer_name"),
                        net_salary=_parse_float(_get(fields, "net_salary")),
                        salary_month=_parse_month(_get(fields, "salary_month")),
                        source_file_ref=slip.get("source_file_ref"),
                        doc_id=f"SALARY_SLIP-{i}",
                        name=_get(fields, "name"),
                    )
                )

        elif doc_type == "BANK_STATEMENT":
            fields = doc["extracted_fields"]
            transactions = [
                BankTransaction(
                    narration=_get(txn, "narration"),
                    amount=_parse_float(_get(txn, "amount")),
                    txn_date=_parse_date(_get(txn, "date")),
                )
                for txn in fields.get("transactions", [])
            ]
            case.bank_statement = BankStatementDoc(
                transactions=transactions,
                source_file_ref=doc.get("source_file_ref"),
                name=_get(fields, "name"),
            )

    return case
