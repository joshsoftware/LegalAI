# Lending POC — Feature Guide

This document explains, in detail, what the validation pipeline behind `POST /cases` does and how each piece works. See [cases_api.md](cases_api.md) for the request/response contract.

## 1. Pipeline overview

`app/services/pipeline.py` orchestrates one end-to-end run in this order:

```
INGEST -> required-document precheck -> GOLDEN RECORD -> IDENTITY VALIDATION
       -> BUSINESS VALIDATION -> SCORING -> DECISION
```

Every step appends a line to an in-memory `audit_log`, giving a readable trail of what happened for a given case (currently returned internally on `PipelineResult`, not yet exposed on the API response).

### 1.1 Required-document precheck

Before anything else runs, the pipeline checks that all of `AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT` are present (`validation_config.REQUIRED_DOCUMENT_TYPES`). If any are missing, the pipeline short-circuits with `decision=FAIL`, `overall_score=0.0`, and reasons like `MISSING_DOCUMENT:PAN` — no golden record or checks are computed.

## 2. Golden Record (`app/services/golden_record.py`)

The Golden Record is the single trusted identity profile for the applicant, built by merging the KYC documents:

- **Address**: sourced from `AADHAAR` only. If Aadhaar carries no address, the Golden Record simply has none — there is no fallback document, and address is not a mandatory Golden Record field, so this does not fail the case.
- **DOB**: `AADHAAR` is primary, `PAN` is a fallback used only when Aadhaar carries no DOB. Both documents print a date of birth, so the two can genuinely disagree; that disagreement is deliberately *not* resolved here — it is left for the DOB check in §3.2 to compare and score. Unlike names there is no "fuller value" to prefer, so this is plain precedence rather than a similarity heuristic.
- **Aadhaar number**: from `AADHAAR`.
- **PAN number**: from `PAN`.
- **Name**: the more interesting case.
  - If only one of Aadhaar/PAN has a name, that one is used.
  - If both have a name, and they're recognizably the same person (`fuzzy.name_similarity` >= `NAME_MATCH_THRESHOLD`, 85), the **fuller** name (more tokens) wins — e.g. "Sneha Sunil Lokhande" over "Sneha Lokhande" — because it carries strictly more identity information.
  - If the two names *aren't* recognizably related, Aadhaar stays authoritative and the mismatch is left for the NAME identity check to flag, rather than silently trusting an unrelated "fuller" name.
- The chosen name is split into `first_name` / `middle_name` / `last_name`.

Each golden field also records its `*_source` (which document it came from), useful for traceability.

## 3. Identity Validation (`app/services/identity_validation.py`)

Two parts:

### 3.1 Mandatory presence check

Regardless of *why* a field is missing, the Golden Record must have `name`, `aadhaar_number`, `pan_number`, and `date_of_birth`. Any missing field produces a failed `ValidationResult` with `failure_reason="missing_in_golden_record"` — and, critically, this is one of the few failures that can force an overall `FAIL` decision outright (see §6).

### 3.2 Per-document cross-checks against the Golden Record

Every document that carries an identity field is compared against the Golden Record:

| Document | Fields checked |
|---|---|
| AADHAAR | name, DOB — *minus whichever it sourced, see §3.3* |
| PAN | name, DOB — *minus whichever it sourced, see §3.3* |
| Each SALARY_SLIP | name |
| BANK_STATEMENT | name |

Matching strategies (`app/matching/`):
- **NAME** — fuzzy string similarity (`fuzzy.name_similarity`), handles reordering (surname-first), initials, and minor spelling differences. Passes at >= 85.
- **DOB** — exact matching (`app.matching.exact`). Result is `MATCH` (score 100), `NO_MATCH` (score 0), or `INCONCLUSIVE` (score 50, e.g. one side missing/unparseable).

**Why only name and DOB.** A comparison is only meaningful when its two sides have independent provenance. Name appears on all four documents and DOB on two (Aadhaar and PAN), so those can genuinely disagree. Address, the Aadhaar number and the PAN number each have exactly **one** source document, and the Golden Record copies that value verbatim — comparing a document's value back against the Golden Record compared a value with itself and always scored 100. Such a check cannot fail, and because `compute_score` renormalizes by observed weight, those guaranteed 100s actively pulled borderline cases *up* toward the pass threshold. Together they accounted for 0.40 of the weight table, all padding.

All three values are still resolved onto the Golden Record and still required to be **present** — `check_mandatory_presence` (§3.1) is unchanged and remains the trigger for the hard-`FAIL` path. "Does this applicant have a PAN at all?" is a real question; "does the PAN match itself?" is not. `exact.aadhaar_match` and `exact.pan_match` are retained in `app/matching/exact.py` (including the masked-Aadhaar suffix logic) for the day a second source appears — e.g. a Form 16 or a KYC-bearing bank statement.

### 3.3 A document is never checked against a value it supplied

The same provenance rule applies one level down, inside the checks that do survive. `build_golden_record` records where each value came from (`name_source`, `dob_source`), and a document is skipped for any field it sourced itself.

Without this, the DOB check was half-blind. With the golden DOB taken from Aadhaar, Aadhaar's own comparison scored a guaranteed 100; a PAN that contradicted it outright scored 0; the component averaged to **50**, not 0 — and at weight 0.10 that was not enough to move a clean case out of `PASS`. Skipping the self-comparison lets a genuine contradiction score 0, which drops such a case to `NEEDS_REVIEW` with reason `DOB:dob_differs`.

The consequence to be aware of: a field whose only source is the document that supplied it now produces **no result at all** rather than a free 100 — e.g. DOB when the PAN extraction yielded none. That is deliberate. The value is present but *uncorroborated*, and `compute_score` renormalizes over observed check types, so contributing nothing is neutral rather than a free pass. (`SALARY_CREDIT_COUNT` always fires for any case that clears the §1 precheck, so the observed weight can never reach zero.)

## 4. Business Validation (`app/services/business_validation.py`)

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

## 5. Scoring (`app/services/scoring.py`)

Given every `ValidationResult` produced above:
1. Scores are grouped by `check_type` and averaged (e.g. if 4 salary slips each produced a `SALARY_DATE` score, they're averaged into one `SALARY_DATE` component score).
2. Each component is weighted per `VALIDATION_WEIGHTS`:

   | Check | Weight |
   |---|---|
   | NAME | 0.15 |
   | DOB | 0.10 |
   | EMPLOYER | 0.10 |
   | SALARY_CREDIT_COUNT | 0.25 |
   | SALARY_CONTINUITY | 0.10 |

   These do not sum to 1.0 and do not need to: step 3 divides by the total weight of the check types actually observed, so they are read as ratios to each other rather than as percentages.

3. The overall score is the weighted average, **renormalized over only the check types actually observed** in this case (so a case missing an optional check type doesn't get unfairly diluted by a zero for a check that never ran).

   Only check types that *can* fail appear in the table. `SALARY_DATE` is excluded because it gates other checks rather than scoring — whether a slip matched drives `EMPLOYER`'s score and `SALARY_CREDIT_COUNT`'s numerator, which carry its influence at a combined 0.35. `AADHAAR` and `PAN` are excluded because they are now only emitted by the mandatory-presence check (§3.2). All three still appear in `component_scores` for display and audit; they simply do not move `overall_score`.

## 6. Decision Engine (`app/services/decision_engine.py`)

Final decision logic, in priority order:

1. **Hard FAIL** — if any mandatory identity field (`NAME`, `AADHAAR`, `PAN`, `DOB`) is missing from the Golden Record entirely (`failure_reason="missing_in_golden_record"`), the case fails immediately regardless of score. Reasons: `MANDATORY_FIELD_MISSING:<CHECK_TYPE>`.
2. **PASS** — if `overall_score >= DECISION_PASS_THRESHOLD` (90).
3. **FAIL** — if `overall_score < DECISION_FAIL_THRESHOLD` (60).
4. **NEEDS_REVIEW** — anything in between (60–90). Reasons list every individual failing check as `<CHECK_TYPE>:<failure_reason>`.

## 7. Persistence (`app/services/persistence.py`)

A successful pipeline run is persisted in a single DB transaction:
- One `Case` row (`applicant_ref`, `status` derived from the decision: PASS/FAIL/NEEDS_REVIEW).
- One `Document` row per submitted document (including one per salary slip), storing `extracted_fields` as JSON.
- One `GoldenRecord` row (name, address, Aadhaar/PAN numbers, DOB).
- One `ValidationResult` row per check performed, linked back to the specific document it was evaluated against where applicable.
- One `PipelineResult` row with the overall score, decision, and reasons.

Document primary keys are resolved via an in-memory `doc_id -> Document.id` map so validation results (which reference documents by string `doc_id` like `"SALARY_SLIP-2"`) can be foreign-keyed correctly.

## 8. Supported document types

| `doc_type` | Purpose |
|---|---|
| `AADHAAR` | Primary identity source (name, address, DOB, Aadhaar number) |
| `PAN` | Secondary identity source (name, PAN number, DOB) |
| `SALARY_SLIP` | Declared income; multiple allowed per case (one per month) |
| `BANK_STATEMENT` | Source of truth for actual salary credits |

## 9. Configuration reference (`app/services/validation_config.py`)

All thresholds/weights are centralized here as plain constants (intended to move into `app/config.py` / environment-driven settings as the app matures, without touching service logic):

| Constant | Value | Meaning |
|---|---|---|
| `NAME_MATCH_THRESHOLD` | 85.0 | Min fuzzy score for NAME to pass |
| `EMPLOYER_MATCH_THRESHOLD` | 80.0 | Min fuzzy score for EMPLOYER to pass |
| `SALARY_CREDIT_EXTRA_MONTHS` | 1 | Months the salary-credit search window extends past the declared month |
| `SALARY_CREDIT_BUFFER_DAYS` | 5 | Days the window starts before the declared month |
| `TXN_SELECTION_EMPLOYER_WEIGHT` | 0.70 | Weight of narration similarity in transaction selection |
| `TXN_SELECTION_AMOUNT_WEIGHT` | 0.30 | Weight of amount closeness in transaction selection |
| `TXN_SELECTION_MIN_SCORE` | 60.0 | Min blended score for a transaction to be selected |
| `SALARY_AMOUNT_TOLERANCE_PCT` | 3.0 | Max % difference between transaction amount and declared net salary to be eligible at all |
| `DECISION_PASS_THRESHOLD` | 90.0 | Min overall score for PASS |
| `DECISION_FAIL_THRESHOLD` | 60.0 | Below this, FAIL; between this and PASS threshold, NEEDS_REVIEW |
| `REQUIRED_DOCUMENT_TYPES` | AADHAAR, PAN, SALARY_SLIP, BANK_STATEMENT | Documents that must be present for the pipeline to proceed |
