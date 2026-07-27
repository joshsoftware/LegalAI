"""
Extraction/validate_llm/test_prompt.py
Standalone tester for the whole-case LLM validation step. Calls the SAME
code the real pipeline uses (llm_field_checks.check_case) so results here
reflect production behavior exactly — no duplicated prompt logic to drift
out of sync.

Usage:
    python Extraction/validate_llm/test_prompt.py
    VALIDATION_MODEL=qwen3:4b python Extraction/validate_llm/test_prompt.py

To add a test case: add an entity to TEST_CASE (a case_entities dict) and
its expected-bad fields to EXPECTED_BAD below.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# shared/config.py requires a full .env (Neo4j, Qdrant, NVIDIA keys) that
# this standalone tester shouldn't need — stub the two values this test
# actually touches before importing anything that chains into config.
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
if "MODEL" in os.environ:
    os.environ["VALIDATION_MODEL"] = os.environ["MODEL"]
os.environ.setdefault("VALIDATION_MODEL", "reaperdoesntrun/Qwen3-0.6B-Distilled")
for _k in ("DATASET_ROOT", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
           "NEO4J_DATABASE", "QDRANT_URL", "QDRANT_COLLECTION",
           "NVIDIA_API_KEY", "EXTRACTION_MODEL", "EMBEDDING_MODEL", "AGENT_MODEL"):
    os.environ.setdefault(_k, "unused-for-this-test")

from Extraction.validate_llm.llm_field_checks import check_case  # noqa: E402

# ── Whole-case test fixture ──────────────────────────────────────────────
# Mirrors real case GJAH220268512019 plus extra entities/fields to check
# whether the model generalizes beyond address/designation without being
# told to, AND correctly leaves alone fields it has no basis to judge.
TEST_CASE = {
    "persons": [
        {"name": "TATA CAPITAL FINANCIAL SERVICE LTD",
         "address": "1) TATA CAPITAL FINANCIAL SERVICE LTD Advocate - D.N.GOSAI",
         "role_in_case": "petitioner"},
        {"name": "VESTITI INDIA",
         "address": "1) VESTITI INDIA",
         "role_in_case": "respondent"},
        {"name": "HEMANT SANDHAVI",
         "role_in_case": "respondent"},
        {"name": "Ramesh Kumar",
         "address": "Flat No 4B, Green Valley Society, Nagpur",
         "role_in_case": "petitioner"},
    ],
    "judges": [
        {"designation": "ADDL. CHIEF METROPOLITAN MAGISTRATE"},
        {"designation": "Ramesh Kumar"},
        {"designation": "Civil Judge Senior Division"},
    ],
    "lawyers": [
        {"name": "D.N.GOSAI"},
        # a field the model has no real basis to judge — should be left alone
        {"name": "S. Mehta", "specialization": "Criminal"},
    ],
    "case_hearings": [
        {"purpose": "PROCESS TO ACCUSED", "nature_of_disposal": None},
        {"purpose": "Disposed", "nature_of_disposal": "LOK ADALAT"},
    ],
}

# (entity_type, index, field) -> should this be flagged as bad?
EXPECTED_BAD = {
    ("persons", 0, "address"),
    ("persons", 1, "address"),
    ("judges", 1, "designation"),
}
# Everything else present in TEST_CASE is expected to be left alone,
# including fields the model has no grounds to judge (name, role_in_case,
# specialization, purpose, nature_of_disposal) and the valid address/
# designation values.


def all_checked_fields():
    for entity_type, entities in TEST_CASE.items():
        for idx, entity in enumerate(entities):
            for field, value in entity.items():
                if value is not None and str(value).strip() != '':
                    yield (entity_type, idx, field, value)


def main():
    model = os.environ["VALIDATION_MODEL"]
    print(f"Model: {model}\n")

    problems = check_case(TEST_CASE, context="TEST-CASE")
    flagged = {(p['entity_type'], p['index'], p['field']) for p in problems}

    print("── Flagged by model (post hallucination-check) ──")
    if not problems:
        print("(none)")
    for p in problems:
        print(f"  {p['entity_type']}[{p['index']}].{p['field']} — {p['reason']}")
    print()

    print("── Results ──")
    passed = 0
    total = 0
    for entity_type, idx, field, value in all_checked_fields():
        total += 1
        key = (entity_type, idx, field)
        expected_bad = key in EXPECTED_BAD
        got_bad = key in flagged
        ok = expected_bad == got_bad
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {entity_type}[{idx}].{field}={value!r} — "
              f"expected {'INVALID' if expected_bad else 'valid'}, "
              f"got {'INVALID' if got_bad else 'valid'}")

    # Any flagged item that isn't in our known-checked-fields set at all
    # (shouldn't happen — check_case already verifies against its own
    # input — but confirms the hallucination backstop end-to-end).
    unexpected = flagged - {(e, i, f) for e, i, f, _ in all_checked_fields()}
    if unexpected:
        print(f"\nWARNING: flagged fields not in test fixture at all: {unexpected}")

    print(f"\n{passed}/{total} passed")


if __name__ == "__main__":
    main()
