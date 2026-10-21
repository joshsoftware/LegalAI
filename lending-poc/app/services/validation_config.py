"""Tunable thresholds/weights for the validation pipeline.

Every constant below is overridable from the environment under the same
name as the constant itself, so retuning a threshold is a config change
rather than a code change.

Values are read from the process environment *and* from .env (the same
file app/config.py reads). Both matter: in Docker, docker-compose.yml's
`env_file: .env` turns .env into real env vars, but on a bare host run
nothing does that -- so the settings class below reads the file directly.

The module-level constants are still the public interface. Services keep
doing `from app.services import validation_config as cfg` and reading
`cfg.NAME_MATCH_THRESHOLD`; nothing outside this file touches the settings
object.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class _ValidationSettings(BaseSettings):
    """Env/.env-backed source for this module's constants.

    Deliberately a separate class from app.config.Settings, not extra
    fields on it: that class has required DATABASE_URL and ENCRYPTION_KEY
    fields, so reusing it would make importing this module (and the scoring
    tests that import it) fail without a database and a key present.
    """

    # extra="ignore" so unrelated .env keys (OLLAMA_*, POSTGRES_*, ...) don't
    # fail validation here.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Comma-separated rather than a JSON array: pydantic parses a list-typed
    # field only from JSON, which is unpleasant to hand-edit in a .env file.
    # Split into the actual list further down.
    REQUIRED_DOCUMENT_TYPES: str = "AADHAAR,PAN,SALARY_SLIP,BANK_STATEMENT"

    NAME_MATCH_THRESHOLD: float = 85.0
    EMPLOYER_MATCH_THRESHOLD: float = 80.0

    SALARY_CREDIT_EXTRA_MONTHS: int = 1
    SALARY_CREDIT_BUFFER_DAYS: int = 5
    TXN_SELECTION_EMPLOYER_WEIGHT: float = 0.70
    TXN_SELECTION_AMOUNT_WEIGHT: float = 0.30
    TXN_SELECTION_MIN_SCORE: float = 60.0

    # A transaction must land within this percentage of the slip's declared
    # net_salary to be eligible as a salary-credit match AT ALL, independent
    # of how well its narration scores. This is what stops a same-employer
    # reimbursement/bonus/advance with a coincidentally close amount from
    # masking a genuinely missing salary credit -- the gate is on the amount
    # itself, not on narration keywords (which don't generalize across
    # employers/languages/formats).
    SALARY_AMOUNT_TOLERANCE_PCT: float = 3.0

    # One field per weight instead of one JSON dict, because *which* check
    # types carry weight is a correctness invariant rather than a knob (see
    # VALIDATION_WEIGHTS below, and test_only_falsifiable_check_types_carry_weight).
    # Env can retune a weight; it cannot add or drop a check type.
    VALIDATION_WEIGHT_NAME: float = 0.15
    VALIDATION_WEIGHT_DOB: float = 0.10
    VALIDATION_WEIGHT_EMPLOYER: float = 0.10
    VALIDATION_WEIGHT_SALARY_CREDIT_COUNT: float = 0.25
    VALIDATION_WEIGHT_SALARY_CONTINUITY: float = 0.10

    DECISION_PASS_THRESHOLD: float = 90.0
    DECISION_FAIL_THRESHOLD: float = 60.0


_settings = _ValidationSettings()

REQUIRED_DOCUMENT_TYPES = [
    doc_type.strip().upper()
    for doc_type in _settings.REQUIRED_DOCUMENT_TYPES.split(",")
    if doc_type.strip()
]

NAME_MATCH_THRESHOLD = _settings.NAME_MATCH_THRESHOLD
EMPLOYER_MATCH_THRESHOLD = _settings.EMPLOYER_MATCH_THRESHOLD

SALARY_CREDIT_EXTRA_MONTHS = _settings.SALARY_CREDIT_EXTRA_MONTHS
SALARY_CREDIT_BUFFER_DAYS = _settings.SALARY_CREDIT_BUFFER_DAYS
TXN_SELECTION_EMPLOYER_WEIGHT = _settings.TXN_SELECTION_EMPLOYER_WEIGHT
TXN_SELECTION_AMOUNT_WEIGHT = _settings.TXN_SELECTION_AMOUNT_WEIGHT
TXN_SELECTION_MIN_SCORE = _settings.TXN_SELECTION_MIN_SCORE

SALARY_AMOUNT_TOLERANCE_PCT = _settings.SALARY_AMOUNT_TOLERANCE_PCT

# Only check types that can actually fail carry weight. ADDRESS, AADHAAR
# and PAN are resolved onto the Golden Record but not cross-checked, since
# each is copied from the very document it would be compared against (see
# identity_validation's module docstring). They are still emitted by
# check_mandatory_presence, which drives the hard-FAIL path -- they simply
# score nothing, and compute_score ignores any check type absent from this
# table.
#
# These weights are not normalized to 1.0 and don't need to be: compute_score
# divides by the total weight of the check types actually observed, so the
# numbers below are read as ratios to each other, not as percentages.
VALIDATION_WEIGHTS = {
    "NAME": _settings.VALIDATION_WEIGHT_NAME,
    "DOB": _settings.VALIDATION_WEIGHT_DOB,
    "EMPLOYER": _settings.VALIDATION_WEIGHT_EMPLOYER,
    "SALARY_CREDIT_COUNT": _settings.VALIDATION_WEIGHT_SALARY_CREDIT_COUNT,
    # Reports statement months the applicant submitted no salary slip for.
    #
    # Deliberately not carved out of SALARY_CREDIT_COUNT's weight: compute_score
    # renormalizes by the weight of check types actually present in a case's
    # results, so a case whose slips cover every statement month emits no
    # SALARY_CONTINUITY results and is scored identically to before this check
    # type existed.
    #
    # Every missing month scores 0.0, so this check's mean is 0.0 whenever it
    # runs at all: it is a binary penalty (~14 points with every other check
    # at 100), not one that scales with how many months are missing.
    "SALARY_CONTINUITY": _settings.VALIDATION_WEIGHT_SALARY_CONTINUITY,
}

DECISION_PASS_THRESHOLD = _settings.DECISION_PASS_THRESHOLD
DECISION_FAIL_THRESHOLD = _settings.DECISION_FAIL_THRESHOLD  # below -> FAIL, between -> NEEDS_REVIEW
