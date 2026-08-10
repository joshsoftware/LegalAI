# Document Validation & Decision Engine — How It Works

## In one sentence

You give it a loan applicant's documents (already extracted into structured
fields by an OCR/extraction pipeline elsewhere) — Aadhaar, PAN, address
proof, salary slips, bank statement — and it gives back one verdict: **PASS,
FAIL, or NEEDS_REVIEW**, plus a full breakdown of exactly which checks
passed, which failed, and why.

It does not read PDFs or images itself. It assumes that's already done and
works only with the structured JSON that comes out of that step.

---

## Input

One JSON object per applicant ("case"), shaped like this:

```json
{
  "applicant_ref": "APP-2026-00123",
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
            "employer_name": "ABC Technologies Pvt Ltd",
            "net_salary": 75000,
            "salary_month": "2026-05"
          },
          "source_file_ref": "s3://kyc-docs/.../salary_slip_may.pdf"
        }
      ]
    },
    {
      "doc_type": "BANK_STATEMENT",
      "extracted_fields": {
        "transactions": [
          { "narration": "ABC TECHNOLOGIES SALARY MAY", "amount": 75000, "date": "2026-06-02" },
          { "narration": "SWIGGY ORDER PAYMENT", "amount": -450, "date": "2026-06-10" }
        ]
      },
      "source_file_ref": "s3://kyc-docs/.../bank_statement.pdf"
    }
  ]
}
```

A few things worth knowing about this shape:

- **Any field can be missing or blank.** Real extraction output is messy —
  an address might not be captured, a DOB might be unreadable. The engine
  treats a missing key, an empty string, and an explicit `null` all the
  same way: as "no value," never as a crash.
- **`SALARY_SLIP` is the one document type that can repeat** — an applicant
  usually has several months of salary slips, each with its own
  `net_salary`, `employer_name`, and `salary_month`.
- **`source_file_ref`** is just kept for traceability (which physical file
  a fact came from) — it doesn't affect any decision.

---

## Output

One decision object, plus a full audit trail of every intermediate
check. In shape:

```
Decision:        PASS | FAIL | NEEDS_REVIEW
Overall score:   0-100
Reasons:         [ "SALARY_DATE:no_matching_credit_in_window", ... ]

Golden Record:   the one trusted identity profile built from all documents
                 (name, address, DOB, Aadhaar, PAN — each tagged with which
                 document it came from)

Validation results: one row per individual check, e.g.
  [PASS] NAME     score=100.00  doc=AADHAAR
  [FAIL] SALARY_DATE  score=0.00  doc=SALARY_SLIP-3  reason=no_matching_credit_in_window

Score breakdown: the weighted average per check type
  NAME 100, ADDRESS 88, AADHAAR 100, ... SALARY_CREDIT_COUNT 75
```

Nothing here is a black box — every number in the final score traces back
to one specific, inspectable check on one specific document.

---

## How it works — the seven stages

```
   Documents in
        │
        ▼
 ① Golden Record          Build ONE trusted identity from all ID documents
        │
        ▼
 ② Identity Validation    Does every document agree with the Golden Record?
        │
        ▼
 ③ Business Validation    Do salary slips have matching bank credits?
        │
        ▼
 ④ Scoring                Combine every check into one weighted number
        │
        ▼
 ⑤ Decision               PASS / FAIL / NEEDS_REVIEW
        │
        ▼
 ⑥ Review (if needed)     A human resolves NEEDS_REVIEW cases
        │
        ▼
 ⑦ Audit                  Every step is permanently logged
```

### ① Golden Record — "who is this person, really?"

Aadhaar and PAN often disagree slightly on name (e.g. Aadhaar has a full
name, PAN has an abbreviated one). Rather than blindly trusting one
document, the engine builds a single reconciled identity:

- **Name**: if Aadhaar and PAN both have a name and they're clearly the
  same person, the **fuller** one wins (more words = more information) —
  e.g. "Sneha Sunil Lokhande" beats "Sneha Lokhande". It's then split into
  first / middle / last name. If the two names don't look related at all,
  Aadhaar stays the trusted source and the mismatch gets flagged later.
- **Address, DOB, Aadhaar number**: taken from Aadhaar; address falls back
  to the address-proof document if Aadhaar didn't have one.
- **PAN number**: taken from the PAN document.
- Every field remembers **which document it came from**, for traceability.

**Mandatory rule**: if name, Aadhaar number, PAN number, or DOB is missing
from *every* document that could supply it, the case is an automatic FAIL —
these are non-negotiable identity anchors.

### ② Identity Validation — "does every document agree?"

Every document is compared against the Golden Record:

| Check | How it's compared |
|---|---|
| **Name** | Fuzzy text match, tolerant of reordering ("Lokhande Sneha" = "Sneha Lokhande") and abbreviation ("Sneha S.L." = "Sneha Sunil Lokhande") |
| **Address** | AI embedding similarity — tolerant of different wording ("Flat 204" vs "Apartment 204") since it compares *meaning*, not exact text |
| **Aadhaar number** | Exact match, with a fallback for masked numbers (e.g. "XXXX XXXX 4321" matches a full number ending in 4321) |
| **PAN number** | Exact match |
| **DOB** | Exact match |

Each of these runs on *every* document that carries that field — Aadhaar,
PAN, address proof, even the salary slips and bank statement if they
happen to carry a name too.

### ③ Business Validation — "is the declared income real?"

This is the more involved stage, because real payroll data is messy: every
company pays on a different day of the month, so the engine never assumes
a fixed payday.

For each salary slip:

1. **Build a window** around that slip's month — a few days before the
   month starts, through the end of the *following* month. This is wide
   enough to catch "pays on the 1st" and "pays on the 5th of next month"
   equally, without any company-specific rules.
2. **Find candidate bank transactions** inside that window that are:
   - credits (positive amount), and
   - within **3% of the declared net salary** — this is a hard cutoff. A
     transaction outside this range is never eligible, no matter how good
     its description looks. (This exists specifically to stop a
     same-employer reimbursement or bonus with a coincidentally close
     amount from being mistaken for the real salary payment.)
3. **Score each remaining candidate** — 70% on how well the transaction's
   description matches the employer name, 30% on how close the amount is —
   and pick the best one.
4. **A transaction can only be used once.** If two slips' windows overlap
   (common, since windows span two months), an earlier slip claims its
   match first so the same bank credit can't "prove" two different months
   of income.
5. If no transaction survives, that slip's `SALARY_DATE` check fails —
   this is a real, visible finding, not silently skipped.

**Employer check** — run separately, *per slip, per month* — verifies that
month's declared employer against *that month's own* matched bank credit
only. It deliberately never compares one month's employer to another's,
because switching jobs mid-history is normal, not suspicious.

**SALARY_CREDIT_COUNT** — one case-level summary: "N salary slips were
declared, how many actually got a verified bank credit?" If an applicant
declares 4 months but only 3 have proof, this shows `3/4 = 75%`. Note that
this **does not by itself fail the case** — it only lowers the overall
score. Missing one month's proof out of several is common and shouldn't
be treated the same as missing proof entirely.

### ④ Scoring — one number from many checks

Every check above produces a score from 0–100. These are grouped by check
type, averaged, and combined into one overall score using fixed weights:

| Check | Weight |
|---|---|
| SALARY_CREDIT_COUNT | 25% (highest — this is the core "is the income real" signal) |
| NAME | 15% |
| AADHAAR | 15% |
| PAN | 15% |
| ADDRESS | 10% |
| DOB | 10% |
| EMPLOYER | 10% |

### ⑤ Decision — turning the score into a verdict

1. If name, Aadhaar, PAN, or DOB is missing entirely → **FAIL**, regardless
   of score.
2. If overall score ≥ 90 → **PASS**.
3. If overall score < 60 → **FAIL**.
4. Otherwise → **NEEDS_REVIEW** — the case isn't clean enough to auto-pass,
   but isn't bad enough to auto-reject either. A human should look at it.

### ⑥ Review

Cases marked NEEDS_REVIEW wait in a queue for a human reviewer, who sees
exactly which checks failed and why, and makes the final call.

### ⑦ Audit

Every stage — ingest, golden record built, each validation run, the final
score, the decision — is logged permanently. Nothing happens invisibly;
you can always answer "why did this case get this verdict?" after the
fact.

---

## Worked example

A real (deliberately imperfect) case run through the engine:

- Aadhaar: "Sneha Sunil Lokhande" — PAN: "Sneha Lokhande" (shorter) →
  Golden Record keeps Aadhaar's fuller name. **PASS.**
- Address worded differently across documents → matched by meaning, not
  exact text. **PASS.**
- 4 salary months declared: March (clean), April (employer switched from
  ABC to Nimbus, both fully verified), May (a decoy reimbursement in the
  same window as the real salary — correctly ignored), June (**no matching
  bank credit exists at all**).
- Result: June's `SALARY_DATE` check **fails** honestly.
  `SALARY_CREDIT_COUNT` drops to 75% (3 of 4 months proven). Two months'
  `EMPLOYER` checks land just under threshold due to how the company names
  compare textually.
- None of this is a single catastrophic failure — it's a mix of solid and
  shaky signals. **Final verdict: NEEDS_REVIEW at 88.4/100** — sent to a
  human rather than auto-approved or auto-rejected.

This is the intended behavior: the engine doesn't try to force every case
into a clean PASS or FAIL. Genuinely ambiguous evidence should produce an
ambiguous verdict.

---

## Try it yourself

```bash
cd lending-poc
python3 scripts/run_demo.py
```

This runs `scripts/sample_case.json` (the example above, in full) through
every stage and prints the Golden Record, every individual check, the
score breakdown, and the final decision.
