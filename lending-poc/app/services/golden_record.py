"""Builds the one trusted identity profile (Golden Record) per applicant.

Field precedence: AADHAAR is the sole source for address. For DOB, AADHAAR
is primary and PAN is a fallback used only when Aadhaar carries none --
both documents print a DOB, so the two can genuinely disagree, and that
disagreement is left for identity_validation's DOB check to score rather
than being silently resolved here. For name specifically: when both
AADHAAR and PAN carry a name, and they're recognizably the same person
(per fuzzy.name_similarity), the fuller of the two (more name tokens) is
preferred as the golden name — e.g. "Ankita Sunil Advitot" over "Ankita
Advitot" — since the fuller version carries strictly more identity
information. If the two names don't look related, AADHAAR stays primary
and the mismatch is left for identity_validation's NAME check to flag,
rather than silently adopting an unrelated "fuller" name.
"""

from app.matching.fuzzy import name_similarity
from app.services import validation_config as cfg
from app.services.dto import CaseInput, GoldenRecord

FULLER_NAME_RELATEDNESS_THRESHOLD = cfg.NAME_MATCH_THRESHOLD


def _split_name(full_name: str) -> tuple[str | None, str | None, str | None]:
    tokens = full_name.split()
    if not tokens:
        return None, None, None
    if len(tokens) == 1:
        return tokens[0], None, None
    if len(tokens) == 2:
        return tokens[0], None, tokens[1]
    return tokens[0], " ".join(tokens[1:-1]), tokens[-1]


def _choose_name(aadhaar_name: str | None, pan_name: str | None) -> tuple[str | None, str]:
    """Returns (chosen_name, source) where source is "AADHAAR" or "PAN"."""
    if aadhaar_name and pan_name:
        related = name_similarity(aadhaar_name, pan_name) >= FULLER_NAME_RELATEDNESS_THRESHOLD
        if related and len(pan_name.split()) > len(aadhaar_name.split()):
            return pan_name, "PAN"
        return aadhaar_name, "AADHAAR"
    if aadhaar_name:
        return aadhaar_name, "AADHAAR"
    if pan_name:
        return pan_name, "PAN"
    return None, "AADHAAR"


def build_golden_record(case: CaseInput) -> GoldenRecord:
    golden = GoldenRecord()

    aadhaar_name = case.aadhaar.name if case.aadhaar else None
    pan_name = case.pan.name if case.pan else None
    chosen_name, name_source_type = _choose_name(aadhaar_name, pan_name)

    if chosen_name is not None:
        golden.name = chosen_name
        golden.name_source = case.aadhaar.doc_id if name_source_type == "AADHAAR" else case.pan.doc_id
        golden.first_name, golden.middle_name, golden.last_name = _split_name(chosen_name)

    if case.aadhaar and case.aadhaar.address is not None:
        golden.address = case.aadhaar.address
        golden.address_source = case.aadhaar.doc_id

    # AADHAAR stays primary; PAN is a fallback only when Aadhaar carries no
    # DOB. Unlike names there is no "fuller" value to prefer -- two dates
    # either agree or they don't -- so this is plain precedence. A genuine
    # disagreement is deliberately NOT resolved here: it is left for
    # identity_validation's DOB check to compare and score.
    if case.aadhaar and case.aadhaar.date_of_birth is not None:
        golden.date_of_birth = case.aadhaar.date_of_birth
        golden.dob_source = case.aadhaar.doc_id
    elif case.pan and case.pan.date_of_birth is not None:
        golden.date_of_birth = case.pan.date_of_birth
        golden.dob_source = case.pan.doc_id

    if case.aadhaar and case.aadhaar.aadhaar_number is not None:
        golden.aadhaar_number = case.aadhaar.aadhaar_number
        golden.aadhaar_source = case.aadhaar.doc_id

    if case.pan and case.pan.pan_number is not None:
        golden.pan_number = case.pan.pan_number
        golden.pan_source = case.pan.doc_id

    return golden
