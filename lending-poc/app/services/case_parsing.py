"""Parses the raw request JSON shape (see docs/cases_api.md) into CaseInput.

Used by the POST /cases endpoint.

Dates and amounts arrive written however the source document printed them --
the values come from an LLM reading a scan, not from a system that agreed to
our contract -- so each one goes through `value_normalization` rather than a
strict strptime.

Parse failures are *collected* rather than raised on the first one, so a
caller sees every bad field in a single 400 instead of discovering them one
round-trip at a time. Critically, `parse_case` raises before returning
whenever anything was collected, which preserves the invariant the rest of
the pipeline relies on: a None on a CaseInput field means the field was
absent from the payload, never that it was present but malformed.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from app.services.dto import (
    AadhaarDoc,
    AddressProofDoc,
    BankStatementDoc,
    BankTransaction,
    CaseInput,
    PanDoc,
    SalarySlipDoc,
)
from app.services.value_normalization import (
    ValueFormatError,
    normalize_amount,
    normalize_date,
    normalize_year_month,
)


@dataclass(frozen=True)
class FieldError:
    """One value that was present in the payload but could not be parsed."""

    document: str  # "AADHAAR", "SALARY_SLIP-0", "BANK_STATEMENT"
    field: str  # "date_of_birth", "transactions[3].amount"
    value: str  # the offending value, echoed back verbatim
    expected: str  # human-readable description of what would have worked
    reason: str  # machine-readable token, e.g. "ambiguous_two_digit_year"


class CaseParseError(ValueError):
    """Raised once at the end of parsing, carrying every field that failed."""

    def __init__(self, errors: list[FieldError]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} field value(s) could not be parsed")


class _Collector:
    """Applies a normalizer, recording failures instead of propagating them."""

    def __init__(self) -> None:
        self.errors: list[FieldError] = []

    def _apply(
        self, fn: Callable[[Any], Any], raw: Any, document: str, field: str
    ) -> Any:
        if raw is None:
            return None
        try:
            return fn(raw)
        except ValueFormatError as exc:
            self.errors.append(
                FieldError(
                    document=document,
                    field=field,
                    value=str(exc.raw),
                    expected=exc.expected,
                    reason=exc.reason,
                )
            )
            return None

    # Named as_* rather than date/month/amount so they don't shadow the
    # `date` type inside this class body.
    def as_date(self, raw: Any, *, document: str, field: str) -> date | None:
        return self._apply(normalize_date, raw, document, field)

    def as_month(self, raw: Any, *, document: str, field: str) -> date | None:
        return self._apply(normalize_year_month, raw, document, field)

    def as_amount(self, raw: Any, *, document: str, field: str) -> float | None:
        return self._apply(normalize_amount, raw, document, field)

    def add(self, *, document: str, field: str, value: str, expected: str, reason: str) -> None:
        """Record a structural problem that isn't a value-format failure."""
        self.errors.append(
            FieldError(
                document=document, field=field, value=value, expected=expected, reason=reason
            )
        )


def _get(fields: dict, key: str) -> Any:
    """Null-safe field lookup: a missing key, JSON null, and an empty/
    whitespace-only string are all treated as no value."""
    value = fields.get(key)
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _text(value: Any) -> str | None:
    """Coerce a scalar to text, so an unquoted number in a string slot (an
    all-digit Aadhaar number, say) still reaches the matching layer as a str."""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def parse_case(payload: dict) -> CaseInput:
    case = CaseInput(applicant_ref=payload["applicant_ref"])
    collect = _Collector()

    for doc in payload["documents"]:
        doc_type = doc["doc_type"]

        if doc_type == "AADHAAR":
            fields = doc["extracted_fields"]
            case.aadhaar = AadhaarDoc(
                name=_get(fields, "name"),
                address=_get(fields, "address"),
                aadhaar_number=_text(_get(fields, "aadhaar_number")),
                date_of_birth=collect.as_date(
                    _get(fields, "date_of_birth"),
                    document="AADHAAR",
                    field="date_of_birth",
                ),
                source_file_ref=doc.get("source_file_ref"),
            )

        elif doc_type == "PAN":
            fields = doc["extracted_fields"]
            case.pan = PanDoc(
                name=_get(fields, "name"),
                pan_number=_text(_get(fields, "pan_number")),
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
                # Collected rather than raised so it aggregates with any
                # field-format problems elsewhere in the payload.
                collect.add(
                    document="SALARY_SLIP",
                    field="salary_slips",
                    value="[]",
                    expected="at least one entry in salary_slips",
                    reason="no_salary_slips",
                )
                continue
            for i, slip in enumerate(slips):
                fields = slip["extracted_fields"]
                doc_id = f"SALARY_SLIP-{i}"
                case.salary_slips.append(
                    SalarySlipDoc(
                        employer_name=_get(fields, "employer_name"),
                        net_salary=collect.as_amount(
                            _get(fields, "net_salary"),
                            document=doc_id,
                            field="net_salary",
                        ),
                        salary_month=collect.as_month(
                            _get(fields, "salary_month"),
                            document=doc_id,
                            field="salary_month",
                        ),
                        source_file_ref=slip.get("source_file_ref"),
                        doc_id=doc_id,
                        name=_get(fields, "name"),
                    )
                )

        elif doc_type == "BANK_STATEMENT":
            fields = doc["extracted_fields"]
            transactions = [
                BankTransaction(
                    narration=_get(txn, "narration"),
                    amount=collect.as_amount(
                        _get(txn, "amount"),
                        document="BANK_STATEMENT",
                        field=f"transactions[{i}].amount",
                    ),
                    txn_date=collect.as_date(
                        _get(txn, "date"),
                        document="BANK_STATEMENT",
                        field=f"transactions[{i}].date",
                    ),
                )
                for i, txn in enumerate(fields.get("transactions", []))
            ]
            case.bank_statement = BankStatementDoc(
                transactions=transactions,
                source_file_ref=doc.get("source_file_ref"),
                name=_get(fields, "name"),
            )

    if collect.errors:
        raise CaseParseError(collect.errors)

    return case
