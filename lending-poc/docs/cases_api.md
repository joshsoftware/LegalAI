# `/cases` API

## What this PR does

Adds the `POST /cases` endpoint, the first user-facing entry point into the lending validation pipeline. It accepts an applicant's KYC and income documents (Aadhaar, PAN, address proof, salary slips, bank statement) as JSON, runs them through identity and business validation, computes an overall confidence score, and returns a PASS / FAIL / NEEDS_REVIEW decision. The full case, its documents, golden record, and validation results are persisted to the database in one transaction.

## Endpoint

`POST /cases`

### Request

```json
{
  "applicant_ref": "APP-2026-00134",
  "documents": [
    {
      "doc_type": "AADHAAR",
      "extracted_fields": {
        "name": "Sneha Sunil Lokhande",
        "address": "Flat 204, Green Heights, Baner, Pune, Maharashtra 411045",
        "aadhaar_number": "XXXX XXXX 4321",
        "date_of_birth": "1995-03-14"
      },
      "source_file_ref": "s3://kyc-docs/APP-2026-00123/aadhaar_front.pdf"
    },
    {
      "doc_type": "PAN",
      "extracted_fields": {
        "name": "Sneha Lokhande",
        "pan_number": "ABCDE1234F"
      },
      "source_file_ref": "s3://kyc-docs/APP-2026-00123/pan_card.pdf"
    },
    {
      "doc_type": "ADDRESS_PROOF",
      "extracted_fields": {
        "address": "Apartment 204, Green Heights, Baner, Pune, MH 411045"
      },
      "source_file_ref": "s3://kyc-docs/APP-2026-00123/address_proof.pdf"
    },
    {
      "doc_type": "SALARY_SLIP",
      "salary_slips": [
        {
          "extracted_fields": {
            "name": "Sneha Sunil Lokhande",
            "employer_name": "ABC Technologies Pvt Ltd",
            "net_salary": 75000,
            "salary_month": "2026-03"
          },
          "source_file_ref": "s3://kyc-docs/APP-2026-00123/salary_slip_march.pdf"
        }
      ]
    },
    {
      "doc_type": "BANK_STATEMENT",
      "extracted_fields": {
        "name": "Lokhande S. S.",
        "transactions": [
          { "narration": "ABC TECHNOLOGIES SALARY MAR", "amount": 75000, "date": "2026-04-01" },
          { "narration": "HOUSE RENT EMI DEBIT", "amount": -18000, "date": "2026-04-03" }
        ]
      },
      "source_file_ref": "s3://kyc-docs/APP-2026-00123/bank_statement_mar_to_jul.pdf"
    }
  ]
}
```

Notes:
- `applicant_ref` and `documents` are required.
- Every document needs `doc_type` and `extracted_fields`; `source_file_ref` is optional.
- `SALARY_SLIP` is the only `doc_type` that carries a `salary_slips` array instead of a flat `extracted_fields` — a case can include multiple salary slips (one per month).
- Required document types for a case to proceed: `AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT`. `ADDRESS_PROOF` is optional (used as an address fallback).

### Response `200 OK`

```json
{
  "case_id": "6e2f6c2a-6a3a-4c1d-9a4b-6f2b6c2a6a3a",
  "applicant_ref": "APP-2026-00134",
  "decision": "NEEDS_REVIEW",
  "overall_score": 88.4,
  "reasons": [
    "SALARY_DATE:no_matching_credit_in_window",
    "EMPLOYER:employer_narration_mismatch"
  ],
  "validation_results": [
    {
      "check_type": "NAME",
      "passed": true,
      "score": 94.5,
      "document_id": "PAN",
      "evidence": null
    },
    {
      "check_type": "SALARY_DATE",
      "passed": false,
      "score": 0.0,
      "document_id": "SALARY_SLIP-3",
      "evidence": { "window": ["2026-05-27", "2026-07-31"] }
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `case_id` | string (UUID) | Primary key of the persisted `Case` row. |
| `applicant_ref` | string | Echoed back from the request. |
| `decision` | string | One of `PASS`, `FAIL`, `NEEDS_REVIEW`. |
| `overall_score` | float | Weighted score (0–100) across all validation checks. |
| `reasons` | string[] | Why this decision was reached (e.g. failing checks, or which mandatory field is missing). |
| `validation_results` | array | One entry per check run, with `check_type`, `passed`, `score`, the `document_id` it applies to, and any supporting `evidence`. |

### Error responses

| Status | When |
|---|---|
| `400 Bad Request` | The request body fails semantic parsing in `parse_case` (e.g. malformed/missing required fields inside `extracted_fields`). |
| `422 Unprocessable Entity` | The request body fails schema validation (wrong types, missing `applicant_ref`/`documents`). |

If any of `AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT` is missing from `documents`, the pipeline still returns `200 OK` with `decision: "FAIL"` and reasons like `MISSING_DOCUMENT:PAN` — this is a business decision, not an HTTP error.
