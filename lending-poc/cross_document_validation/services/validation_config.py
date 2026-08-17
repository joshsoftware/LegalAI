"""Tunable thresholds/weights for the validation pipeline.

Plain constants for this standalone, no-DB run. When this integrates with
the rest of the app, these move into app/config.py (pydantic Settings,
loaded from .env) without changing any service logic that reads them.
"""

REQUIRED_DOCUMENT_TYPES = ["AADHAAR", "PAN", "SALARY_SLIP", "BANK_STATEMENT"]

NAME_MATCH_THRESHOLD = 85.0
EMPLOYER_MATCH_THRESHOLD = 80.0
ADDRESS_SIMILARITY_THRESHOLD = 0.55  # cosine, 0-1 (stub embeddings are coarser than real ones)

SALARY_CREDIT_EXTRA_MONTHS = 1
SALARY_CREDIT_BUFFER_DAYS = 5
TXN_SELECTION_EMPLOYER_WEIGHT = 0.70
TXN_SELECTION_AMOUNT_WEIGHT = 0.30
TXN_SELECTION_MIN_SCORE = 60.0

# A transaction must land within this percentage of the slip's declared
# net_salary to be eligible as a salary-credit match AT ALL, independent
# of how well its narration scores. This is what stops a same-employer
# reimbursement/bonus/advance with a coincidentally close amount from
# masking a genuinely missing salary credit -- the gate is on the amount
# itself, not on narration keywords (which don't generalize across
# employers/languages/formats).
SALARY_AMOUNT_TOLERANCE_PCT = 3.0

VALIDATION_WEIGHTS = {
    "NAME": 0.15,
    "ADDRESS": 0.10,
    "AADHAAR": 0.15,
    "PAN": 0.15,
    "DOB": 0.10,
    "EMPLOYER": 0.10,
    "SALARY_CREDIT_COUNT": 0.25,
}

DECISION_PASS_THRESHOLD = 90.0
DECISION_FAIL_THRESHOLD = 60.0  # below -> FAIL, between -> NEEDS_REVIEW
