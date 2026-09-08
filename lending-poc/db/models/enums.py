"""Enums shared by DB models and the validation pipeline's in-memory DTOs.

Owned by the DB layer since they back Postgres enum columns; the pipeline
layer (app.services.dto) imports these rather than redefining them.
"""

from enum import Enum


class DocType(str, Enum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    # Retired: no longer accepted by the API or produced by the pipeline.
    # Kept because this backs a Postgres enum (documents.doc_type) that may
    # still hold ADDRESS_PROOF in historical rows, and Postgres has no
    # ALTER TYPE ... DROP VALUE -- removing it means recreating the type and
    # rewriting the column (see 0009's note on the same problem for check_type).
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
    SALARY_CONTINUITY = "SALARY_CONTINUITY"
    MANDATORY_PRESENCE = "MANDATORY_PRESENCE"


class Decision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
