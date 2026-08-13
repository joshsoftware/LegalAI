"""Enums shared by DB models and the validation pipeline's in-memory DTOs.

Owned by the DB layer since they back Postgres enum columns; the pipeline
layer (app.services.dto) imports these rather than redefining them.
"""

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
