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
| `400 Bad Request` | One or more values inside `extracted_fields` could not be parsed. |
| `422 Unprocessable Entity` | The request body fails schema validation (wrong types, missing `applicant_ref`/`documents`). |

#### Value formats

The formats shown above are canonical, but the endpoint is **tolerant on input** —
values usually originate from an LLM reading a scanned document, so they arrive
written however the document printed them. `app/services/value_normalization.py`
accepts, among others:

| Field | Also accepted |
|---|---|
| dates | `14-03-1995`, `14/03/1995`, `2026/03/14`, `14 March 1995`, `14-Mar-1995` |
| `salary_month` | a full date (truncated to its month), `03/2026`, `March 2026`, `Aug 2026` |
| amounts | `"75,000"`, `"1,23,456"`, `"Rs. 45,000/-"`, `"₹75,000"`, `"$ 4,500.00"`, `"(18,000)"`, `"18,000 Dr"` |

Ambiguous day/month ordering (e.g. `03/04/2026`, where both parts could be a
month) resolves **day-first**, per `AMBIGUOUS_DATE_ORDER`. Two-digit years are
rejected rather than guessed at.

A value that is *absent* (missing key, `null`, or blank) is fine — the pipeline
reports it as a missing field. A value that is *present but unparseable* is
never silently dropped, because a dropped value would surface downstream as a
confident, wrong decision. Instead every such value is collected and returned
together:

```json
{
  "detail": {
    "error": "invalid_field_format",
    "message": "2 field value(s) could not be parsed.",
    "fields": [
      {
        "document": "AADHAAR",
        "field": "date_of_birth",
        "value": "14-03-95",
        "expected": "a date such as 1995-03-14, 14-03-1995, 14/03/1995 or '14 March 1995'",
        "reason": "ambiguous_two_digit_year"
      },
      {
        "document": "BANK_STATEMENT",
        "field": "transactions[1].amount",
        "value": "abc",
        "expected": "a number such as 75000, '75,000' or 'Rs. 75,000.00'",
        "reason": "unrecognised_amount_format"
      }
    ]
  }
}
```

Structural problems that are not per-field format failures still return a plain
string `detail`, so clients should handle both shapes.

If any of `AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT` is missing from `documents`, the pipeline still returns `200 OK` with `decision: "FAIL"` and reasons like `MISSING_DOCUMENT:PAN` — this is a business decision, not an HTTP error.
