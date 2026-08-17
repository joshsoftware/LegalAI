# Lending POC — Feature Guide

This document explains, in detail, what the validation pipeline behind `POST /cases` does and how each piece works. See [cases_api.md](cases_api.md) for the request/response contract.

## 1. Pipeline overview

`cross_document_validation/services/pipeline.py` orchestrates one end-to-end run in this order:

```
INGEST -> required-document precheck -> GOLDEN RECORD -> IDENTITY VALIDATION
       -> BUSINESS VALIDATION -> SCORING -> DECISION
```

Every step appends a line to an in-memory `audit_log`, giving a readable trail of what happened for a given case (currently returned internally on `PipelineResult`, not yet exposed on the API response).

### 1.1 Required-document precheck

Before anything else runs, the pipeline checks that all of `AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT` are present (`validation_config.REQUIRED_DOCUMENT_TYPES`). If any are missing, the pipeline short-circuits with `decision=FAIL`, `overall_score=0.0`, and reasons like `MISSING_DOCUMENT:PAN` — no golden record or checks are computed.

## 2. Golden Record (`cross_document_validation/services/golden_record.py`)

The Golden Record is the single trusted identity profile for the applicant, built by merging the KYC documents:

- **Address & DOB**: sourced from `AADHAAR`. If Aadhaar has no address, `ADDRESS_PROOF` is used as a fallback.
- **Aadhaar number**: from `AADHAAR`.
- **PAN number**: from `PAN`.
- **Name**: the more interesting case.
  - If only one of Aadhaar/PAN has a name, that one is used.
  - If both have a name, and they're recognizably the same person (`fuzzy.name_similarity` >= `NAME_MATCH_THRESHOLD`, 85), the **fuller** name (more tokens) wins — e.g. "Sneha Sunil Lokhande" over "Sneha Lokhande" — because it carries strictly more identity information.
  - If the two names *aren't* recognizably related, Aadhaar stays authoritative and the mismatch is left for the NAME identity check to flag, rather than silently trusting an unrelated "fuller" name.
- The chosen name is split into `first_name` / `middle_name` / `last_name`.
- If an address was resolved, an address embedding is computed (`cross_document_validation.matching.embeddings.get_address_embedding`) and stored for later similarity checks.

Each golden field also records its `*_source` (which document it came from), useful for traceability.

## 3. Identity Validation (`cross_document_validation/services/identity_validation.py`)

Two parts:

### 3.1 Mandatory presence check

Regardless of *why* a field is missing, the Golden Record must have `name`, `aadhaar_number`, `pan_number`, and `date_of_birth`. Any missing field produces a failed `ValidationResult` with `failure_reason="missing_in_golden_record"` — and, critically, this is one of the few failures that can force an overall `FAIL` decision outright (see §6).

### 3.2 Per-document cross-checks against the Golden Record

Every document that carries an identity field is compared against the Golden Record:

| Document | Fields checked |
|---|---|
| AADHAAR | name, address, aadhaar_number, DOB |
| PAN | name, pan_number |
| ADDRESS_PROOF | address |
| Each SALARY_SLIP | name |
| BANK_STATEMENT | name |

Matching strategies (`cross_document_validation/matching/`):
- **NAME** — fuzzy string similarity (`fuzzy.name_similarity`), handles reordering (surname-first), initials, and minor spelling differences. Passes at >= 85.
- **ADDRESS** — embedding cosine similarity (`embeddings.address_similarity`), tolerant of differently-worded but equivalent addresses (e.g. "Apartment" vs "Flat", "MH" vs "Maharashtra"). Passes at >= 0.55 similarity (scored as similarity × 100).
- **AADHAAR / PAN / DOB** — exact matching (`cross_document_validation.matching.exact`). Result is `MATCH` (score 100), `NO_MATCH` (score 0), or `INCONCLUSIVE` (score 50, e.g. one side missing/unparseable).

## 4. Business Validation (`cross_document_validation/services/business_validation.py`)

Verifies that declared income (salary slips) is corroborated by actual bank activity. Only runs if both salary slips and a bank statement are present.

### 4.1 Salary-credit matching (`SALARY_DATE` check)

For each salary slip:
1. A **month-level search window** is built around the slip's declared `salary_month`: starts `SALARY_CREDIT_BUFFER_DAYS` (5) days before the month begins, and extends `SALARY_CREDIT_EXTRA_MONTHS` (1) month past it. No specific payroll day is assumed.
2. Within that window, candidate transactions must be **credits** (`amount > 0`) and within `SALARY_AMOUNT_TOLERANCE_PCT` (3%) of the slip's declared `net_salary`. This amount gate is applied *before* narration scoring — it's what prevents a same-employer reimbursement/bonus with a coincidentally close amount from masking a genuinely missing salary credit.
3. Among eligible candidates, each is scored as a weighted blend of employer-name similarity to the transaction narration (`TXN_SELECTION_EMPLOYER_WEIGHT`, 0.70) and amount closeness (`TXN_SELECTION_AMOUNT_WEIGHT`, 0.30). The highest-scoring candidate is selected, provided its score clears `TXN_SELECTION_MIN_SCORE` (60).
4. Once a transaction is claimed by a slip, it's excluded from consideration for other slips in the same case (prevents one bank credit being counted as evidence for two different months, which can happen since windows overlap).
5. If no eligible transaction is found, the check fails with `failure_reason="no_matching_credit_in_window"`.

Slips are resolved in chronological order (earliest `salary_month` first) so earlier months get first claim on ambiguous transactions, but results are returned in the original request order.

### 4.2 Employer consistency (`EMPLOYER` check)

Each slip's declared `employer_name` is compared — via fuzzy similarity — only against the narration of **that same slip's own matched transaction** (never against another month's slip or employer). This is intentional: a legitimate employer switch mid-history (e.g. a job change) should not penalize either month. Passes at similarity >= `EMPLOYER_MATCH_THRESHOLD` (80). If the slip had no matched transaction to begin with, this check automatically fails with `failure_reason="no_matching_credit_to_verify_employer_against"`.

### 4.3 Salary credit count (`SALARY_CREDIT_COUNT` check)

An aggregate check: `matched_slips / total_slips × 100`. It passes only if *every* slip matched a transaction, but a partial match (e.g. 3 of 4 months) doesn't hard-fail the case — it only lowers this component's score, which feeds into the weighted overall score. Evidence includes the bank statement's observed date range and match counts.

## 5. Scoring (`cross_document_validation/services/scoring.py`)

Given every `ValidationResult` produced above:
1. Scores are grouped by `check_type` and averaged (e.g. if 4 salary slips each produced a `SALARY_DATE` score, they're averaged into one `SALARY_DATE` component score).
2. Each component is weighted per `VALIDATION_WEIGHTS`:

   | Check | Weight |
   |---|---|
   | NAME | 0.15 |
   | ADDRESS | 0.10 |
   | AADHAAR | 0.15 |
   | PAN | 0.15 |
   | DOB | 0.10 |
   | EMPLOYER | 0.10 |
   | SALARY_CREDIT_COUNT | 0.25 |

3. The overall score is the weighted average, **renormalized over only the check types actually observed** in this case (so a case missing an optional check type doesn't get unfairly diluted by a zero for a check that never ran). Note `SALARY_DATE` itself isn't in the weight table — it gates whether a credit was found at all, but the weighted score is driven by `EMPLOYER` and `SALARY_CREDIT_COUNT`.

## 6. Decision Engine (`cross_document_validation/services/decision_engine.py`)

Final decision logic, in priority order:

1. **Hard FAIL** — if any mandatory identity field (`NAME`, `AADHAAR`, `PAN`, `DOB`) is missing from the Golden Record entirely (`failure_reason="missing_in_golden_record"`), the case fails immediately regardless of score. Reasons: `MANDATORY_FIELD_MISSING:<CHECK_TYPE>`.
2. **PASS** — if `overall_score >= DECISION_PASS_THRESHOLD` (90).
3. **FAIL** — if `overall_score < DECISION_FAIL_THRESHOLD` (60).
4. **NEEDS_REVIEW** — anything in between (60–90). Reasons list every individual failing check as `<CHECK_TYPE>:<failure_reason>`.

## 7. Persistence (`cross_document_validation/services/persistence.py`)

A successful pipeline run is persisted in a single DB transaction:
- One `Case` row (`applicant_ref`, `status` derived from the decision: PASS/FAIL/NEEDS_REVIEW).
- One `Document` row per submitted document (including one per salary slip), storing `extracted_fields` as JSON.
- One `GoldenRecord` row (name, address + embedding, Aadhaar/PAN numbers, DOB).
- One `ValidationResult` row per check performed, linked back to the specific document it was evaluated against where applicable.
- One `PipelineResult` row with the overall score, decision, and reasons.

Document primary keys are resolved via an in-memory `doc_id -> Document.id` map so validation results (which reference documents by string `doc_id` like `"SALARY_SLIP-2"`) can be foreign-keyed correctly.

## 8. Supported document types

| `doc_type` | Purpose |
|---|---|
| `AADHAAR` | Primary identity source (name, address, DOB, Aadhaar number) |
| `PAN` | Secondary identity source (name, PAN number) |
| `ADDRESS_PROOF` | Address fallback if Aadhaar has none |
| `SALARY_SLIP` | Declared income; multiple allowed per case (one per month) |
| `BANK_STATEMENT` | Source of truth for actual salary credits |

## 9. Configuration reference (`cross_document_validation/services/validation_config.py`)

All thresholds/weights are centralized here as plain constants (intended to move into `app/config.py` / environment-driven settings as the app matures, without touching service logic):

| Constant | Value | Meaning |
|---|---|---|
| `NAME_MATCH_THRESHOLD` | 85.0 | Min fuzzy score for NAME to pass |
| `EMPLOYER_MATCH_THRESHOLD` | 80.0 | Min fuzzy score for EMPLOYER to pass |
| `ADDRESS_SIMILARITY_THRESHOLD` | 0.55 | Min cosine similarity for ADDRESS to pass |
| `SALARY_CREDIT_EXTRA_MONTHS` | 1 | Months the salary-credit search window extends past the declared month |
| `SALARY_CREDIT_BUFFER_DAYS` | 5 | Days the window starts before the declared month |
| `TXN_SELECTION_EMPLOYER_WEIGHT` | 0.70 | Weight of narration similarity in transaction selection |
| `TXN_SELECTION_AMOUNT_WEIGHT` | 0.30 | Weight of amount closeness in transaction selection |
| `TXN_SELECTION_MIN_SCORE` | 60.0 | Min blended score for a transaction to be selected |
| `SALARY_AMOUNT_TOLERANCE_PCT` | 3.0 | Max % difference between transaction amount and declared net salary to be eligible at all |
| `DECISION_PASS_THRESHOLD` | 90.0 | Min overall score for PASS |
| `DECISION_FAIL_THRESHOLD` | 60.0 | Below this, FAIL; between this and PASS threshold, NEEDS_REVIEW |
| `REQUIRED_DOCUMENT_TYPES` | AADHAAR, PAN, SALARY_SLIP, BANK_STATEMENT | Documents that must be present for the pipeline to proceed |
