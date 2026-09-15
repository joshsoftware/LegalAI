"""Plain in-memory data structures for the validation pipeline.

No database/ORM involved yet — these dataclasses are what the extraction
pipeline's JSON gets parsed into, and what every service function passes
around. When persistence is added later, these become the shape that gets
mapped to/from the DB models, but the validation logic itself does not
change.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class DocType(str, Enum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    ADDRESS_PROOF = "ADDRESS_PROOF"
    SALARY_SLIP = "SALARY_SLIP"
    BANK_STATEMENT = "BANK_STATEMENT"


class CheckType(str, Enum):
    NAME = "NAME"
    ADDRESS = "ADDRESS"
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    DOB = "DOB"
    EMPLOYER = "EMPLOYER"
    SALARY_DATE = "SALARY_DATE"
    SALARY_CREDIT_COUNT = "SALARY_CREDIT_COUNT"
    MANDATORY_PRESENCE = "MANDATORY_PRESENCE"


class Decision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class AadhaarDoc:
    name: str | None = None
    address: str | None = None
    aadhaar_number: str | None = None
    date_of_birth: date | None = None
    source_file_ref: str | None = None
    doc_id: str = "AADHAAR"


@dataclass
class PanDoc:
    name: str | None = None
    pan_number: str | None = None
    source_file_ref: str | None = None
    doc_id: str = "PAN"


@dataclass
class AddressProofDoc:
    address: str | None = None
    source_file_ref: str | None = None
    doc_id: str = "ADDRESS_PROOF"


@dataclass
class SalarySlipDoc:
    doc_id: str
    employer_name: str | None = None
    net_salary: float | None = None
    salary_month: date | None = None  # first-of-month
    name: str | None = None
    source_file_ref: str | None = None


@dataclass
class BankTransaction:
    narration: str | None = None
    amount: float | None = None
    txn_date: date | None = None


@dataclass
class BankStatementDoc:
    transactions: list[BankTransaction]
    doc_id: str = "BANK_STATEMENT"
    name: str | None = None
    source_file_ref: str | None = None


@dataclass
class CaseInput:
    applicant_ref: str
    aadhaar: AadhaarDoc | None = None
    pan: PanDoc | None = None
    address_proof: AddressProofDoc | None = None
    salary_slips: list[SalarySlipDoc] = field(default_factory=list)
    bank_statement: BankStatementDoc | None = None

    def present_doc_types(self) -> set[str]:
        present = set()
        if self.aadhaar:
            present.add(DocType.AADHAAR.value)
        if self.pan:
            present.add(DocType.PAN.value)
        if self.address_proof:
            present.add(DocType.ADDRESS_PROOF.value)
        if self.salary_slips:
            present.add(DocType.SALARY_SLIP.value)
        if self.bank_statement:
            present.add(DocType.BANK_STATEMENT.value)
        return present


@dataclass
class GoldenRecord:
    name: str | None = None
    name_source: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    address: str | None = None
    address_source: str | None = None
    address_embedding: list[float] = field(default_factory=list)
    date_of_birth: date | None = None
    dob_source: str | None = None
    aadhaar_number: str | None = None
    aadhaar_source: str | None = None
    pan_number: str | None = None
    pan_source: str | None = None


@dataclass
class ValidationResult:
    check_type: CheckType
    passed: bool
    score: float
    document_id: str | None = None
    failure_reason: str | None = None
    evidence: dict | None = None  # in-memory only; becomes real columns/FKs once persisted


@dataclass
class ScoreResult:
    overall_score: float
    component_scores: dict[str, float]


@dataclass
class DecisionResult:
    decision: Decision
    reasons: list[str]
    overall_score: float


@dataclass
class PipelineResult:
    golden_record: GoldenRecord | None
    validation_results: list[ValidationResult]
    score_result: ScoreResult | None
    decision_result: DecisionResult
    audit_log: list[str]
