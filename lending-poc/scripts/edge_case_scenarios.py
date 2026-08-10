"""Runs a battery of edge-case scenarios through the validation pipeline,
starting from the base sample_case.json and mutating it per scenario, to
show exactly what today's code does and does not handle correctly.

Usage:
    python scripts/edge_case_scenarios.py
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_demo import parse_case  # noqa: E402
from app.services.pipeline import run_pipeline  # noqa: E402


def load_base() -> dict:
    path = Path(__file__).resolve().parent / "sample_case.json"
    return json.loads(path.read_text())


def summarize(label: str, payload: dict) -> None:
    case = parse_case(payload)
    result = run_pipeline(case)

    print("=" * 78)
    print(label)
    print("=" * 78)
    print(f"  decision = {result.decision_result.decision.value}  "
          f"score = {result.decision_result.overall_score:.2f}")
    print(f"  reasons  = {result.decision_result.reasons}")

    for r in result.validation_results:
        if r.check_type.value in ("SALARY_DATE", "EMPLOYER", "SALARY_CREDIT_COUNT"):
            status = "PASS" if r.passed else "FAIL"
            doc = f" doc={r.document_id}" if r.document_id else ""
            print(f"    [{status}] {r.check_type.value:<20} score={r.score:6.2f}{doc}")
            if r.evidence and "matched_transaction" in r.evidence:
                txn = r.evidence["matched_transaction"]
                print(f"             -> matched: {txn.narration!r} amount={txn.amount} date={txn.txn_date}")
            elif r.evidence and r.check_type.value == "SALARY_CREDIT_COUNT":
                print(f"             evidence: {r.evidence}")
    print()


def scenario_reimbursement_ambiguity() -> None:
    """A reimbursement credit sits inside the same month-window as the real
    salary credit, from the same employer. Does the 70/30 scoring correctly
    prefer the salary-sized credit over the reimbursement?
    """
    payload = load_base()
    # Base data already has this: May slip window contains both the
    # "SALARY MAY" (75000) and "REIMBURSEMENT" (4500) transactions.
    summarize("1. Reimbursement in same window as real salary credit (baseline)", payload)

    # Harder version: reimbursement amount is much closer to net_salary,
    # to see if amount-closeness alone could fool the selection.
    payload2 = load_base()
    for doc in payload2["documents"]:
        if doc["doc_type"] == "BANK_STATEMENT":
            for txn in doc["extracted_fields"]["transactions"]:
                if "REIMBURSEMENT" in txn["narration"]:
                    txn["amount"] = 74000  # suspiciously close to net_salary (75000)
    summarize(
        "1b. Reimbursement amount very close to net_salary (adversarial)", payload2
    )


def scenario_partial_slip_match() -> None:
    """3 salary slips declared, bank statement only backs 2 of them.
    Per spec (README 'Open decisions'), this must NOT hard-fail the case —
    only lower SALARY_CREDIT_COUNT's score. Confirm that's actually true.
    """
    payload = load_base()
    for doc in payload["documents"]:
        if doc["doc_type"] == "SALARY_SLIP":
            doc["salary_slips"].append(
                {
                    "extracted_fields": {
                        "employer_name": "ABC Technologies Pvt Ltd",
                        "net_salary": 75000,
                        "salary_month": "2026-07",
                    },
                    "source_file_ref": "s3://kyc-docs/APP-2026-00123/salary_slip_july.pdf",
                }
            )
            # No corresponding July bank credit exists in the base data.
    summarize("2. 3 slips declared, only 2 have matching bank credits", payload)


def scenario_salary_amount_changed() -> None:
    """Net salary changes month-to-month (raise or deduction). Each slip's
    amount-closeness should be judged against its OWN declared net_salary,
    not a fixed/previous value.
    """
    payload = load_base()
    for doc in payload["documents"]:
        if doc["doc_type"] == "SALARY_SLIP":
            for slip in doc["salary_slips"]:
                if slip["extracted_fields"]["salary_month"] == "2026-06":
                    slip["extracted_fields"]["net_salary"] = 82000  # a raise
        if doc["doc_type"] == "BANK_STATEMENT":
            for txn in doc["extracted_fields"]["transactions"]:
                if "JUN" in txn["narration"]:
                    txn["amount"] = 82000  # bank credit reflects the raise
    summarize("3. Salary raised in June (75000 -> 82000), bank credit matches", payload)

    # Now the adversarial version: slip says raise, but bank credit still
    # shows the OLD amount -- should this still confidently match?
    payload2 = load_base()
    for doc in payload2["documents"]:
        if doc["doc_type"] == "SALARY_SLIP":
            for slip in doc["salary_slips"]:
                if slip["extracted_fields"]["salary_month"] == "2026-06":
                    slip["extracted_fields"]["net_salary"] = 82000
        # bank statement untouched: still shows 75000 for June
    summarize(
        "3b. Slip claims raise to 82000 but bank credit still shows 75000", payload2
    )


def scenario_employer_switch() -> None:
    """Applicant switched jobs: earlier slips are Employer A, most recent
    slip(s) are Employer B, with matching bank credits from each. Does
    EMPLOYER consistency correctly distinguish "job switch" from "identity
    fraud", or does it just uniformly fail?
    """
    payload = load_base()
    for doc in payload["documents"]:
        if doc["doc_type"] == "SALARY_SLIP":
            # May slip: old employer. June slip: new employer (switched).
            for slip in doc["salary_slips"]:
                if slip["extracted_fields"]["salary_month"] == "2026-06":
                    slip["extracted_fields"]["employer_name"] = "NextGen Solutions Pvt Ltd"
        if doc["doc_type"] == "BANK_STATEMENT":
            for txn in doc["extracted_fields"]["transactions"]:
                if "JUN" in txn["narration"]:
                    txn["narration"] = "NEXTGEN SOLUTIONS SALARY JUN"
    summarize("4. Employer switched between May (ABC) and June (NextGen)", payload)


if __name__ == "__main__":
    scenario_reimbursement_ambiguity()
    scenario_partial_slip_match()
    scenario_salary_amount_changed()
    scenario_employer_switch()
