"""Runs one dummy case through the validation pipeline end-to-end, with no
database involved. Parses scripts/sample_case.json (the README's exact
sample payload) into in-memory DTOs, runs the pipeline, and prints every
intermediate result plus the final decision.

Usage:
    python scripts/run_demo.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.case_parsing import parse_case  # noqa: E402
from app.services.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    sample_path = Path(__file__).resolve().parent / "sample_case.json"
    payload = json.loads(sample_path.read_text())
    case = parse_case(payload)

    result = run_pipeline(case)

    print("=" * 70)
    print(f"Applicant: {case.applicant_ref}")
    print("=" * 70)

    print("\n--- Audit log ---")
    for line in result.audit_log:
        print(f"  {line}")

    if result.golden_record:
        g = result.golden_record
        print("\n--- Golden Record ---")
        print(f"  name             = {g.name!r} (source: {g.name_source})")
        print(f"    first_name     = {g.first_name!r}")
        print(f"    middle_name    = {g.middle_name!r}")
        print(f"    last_name      = {g.last_name!r}")
        print(f"  address          = {g.address!r} (source: {g.address_source})")
        print(f"  date_of_birth    = {g.date_of_birth} (source: {g.dob_source})")
        print(f"  aadhaar_number   = {g.aadhaar_number!r} (source: {g.aadhaar_source})")
        print(f"  pan_number       = {g.pan_number!r} (source: {g.pan_source})")

    print("\n--- Validation results ---")
    for r in result.validation_results:
        status = "PASS" if r.passed else "FAIL"
        doc = f" doc={r.document_id}" if r.document_id else ""
        reason = f" reason={r.failure_reason}" if r.failure_reason else ""
        print(f"  [{status}] {r.check_type.value:<22} score={r.score:6.2f}{doc}{reason}")
        if r.evidence:
            print(f"           evidence={r.evidence}")

    if result.score_result:
        print("\n--- Score ---")
        print(f"  overall_score = {result.score_result.overall_score:.2f}")
        print("  component_scores:")
        for check_type, score in result.score_result.component_scores.items():
            print(f"    {check_type:<22} {score:.2f}")

    print("\n--- Decision ---")
    print(f"  decision = {result.decision_result.decision.value}")
    print(f"  overall_score = {result.decision_result.overall_score:.2f}")
    print(f"  reasons = {result.decision_result.reasons}")
    print("=" * 70)


if __name__ == "__main__":
    main()
