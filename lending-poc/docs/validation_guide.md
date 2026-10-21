# How Your Documents Are Validated

A plain-language guide to what the system checks, what it takes to pass, and
why a case gets held for review.

---

## 1. The short version

You submit four documents. The system pulls the details out of them, builds
one merged profile of who you are, then asks a single question:

> **Do these four documents tell the same story?**

It answers with a score from 0 to 100 and one of three outcomes:

| Score | Outcome | What it means |
|-------|---------|---------------|
| 90 or above | **PASS** | The documents agree. Nothing further needed. |
| 60 to 89 | **NEEDS_REVIEW** | Something didn't line up. A person looks at it. |
| Below 60 | **FAIL** | Too much disagreement to proceed. |

There is also a fast **FAIL** that ignores the score entirely, described in
section 4. A missing PAN cannot be outweighed by a perfect salary history.

---

## 2. What you must submit

All four of these are required. If any one is missing, validation stops
immediately with **FAIL** and a score of 0 — no other check is even run.

| Document | What is read from it |
|----------|----------------------|
| **Aadhaar card** | Name, date of birth, Aadhaar number, address |
| **PAN card** | Name, date of birth, PAN number |
| **Salary slips** | Employer name, net salary, salary month (one slip per month; several allowed) |
| **Bank statement** | Account holder name, and every transaction with date, amount and narration |

The reason given is specific, e.g. `MISSING_DOCUMENT:PAN`.

---

## 3. How your identity profile is built

Before checking anything, the system merges your documents into one trusted
profile called the **Golden Record**. Each field has a defined source:

| Field | Where it comes from |
|-------|---------------------|
| **Name** | Aadhaar, or PAN if the PAN name is *fuller* and clearly the same person — e.g. "Arjun Ramesh Iyer" is preferred over "Arjun Iyer" |
| **Date of birth** | Aadhaar. If your Aadhaar has no readable DOB, PAN is used instead |
| **Aadhaar number** | Aadhaar card |
| **PAN number** | PAN card |
| **Address** | Aadhaar card |

**One rule matters for understanding your result:** a document is never
checked against a value it supplied itself. If your date of birth came from
your Aadhaar, your Aadhaar's DOB is not "verified" against itself — only
your PAN's DOB is a real test. Comparing a value with its own copy would
always succeed and would tell nobody anything.

---

## 4. Checks that cause an immediate FAIL

These are pass/fail. No score can compensate for them.

### 4.1 A required document is missing

See section 2. Reason: `MISSING_DOCUMENT:<TYPE>`.

### 4.2 A required identity field is missing

After merging, the Golden Record must contain **all four** of:

- Name
- Aadhaar number
- PAN number
- Date of birth

If any is absent — because it wasn't on the document, or couldn't be read
from the scan — the case fails outright. Reason:
`MANDATORY_FIELD_MISSING:PAN` (or `NAME`, `AADHAAR`, `DOB`).

This is about the value being **present**, not about it matching anything.
"Do you have a PAN at all?" is the question here.

### 4.3 A value is present but unreadable

If a date or amount is written in a form the system cannot interpret, the
submission is rejected before scoring, with every bad field listed at once
so you can fix them in a single pass.

Dates are read flexibly — `1994-08-19`, `19/08/1994` and `19-Aug-1994` are
all accepted. What is rejected is genuine ambiguity, such as a two-digit
year (`14-03-95`), where the system refuses to guess. Amounts tolerate the
way documents actually print them: `88000`, `88,000` and `Rs. 88,000` all
work.

---

## 5. The scored checks

Everything below produces a score from 0 to 100 rather than a yes or no.
This is deliberate: scanned documents are messy, names get abbreviated, and
employers rarely write their full legal name on a bank narration. A rigid
exact-match rule would reject honest applicants.

### 5.1 NAME — weight 0.15

Your name is compared across **every** document that carries one: Aadhaar,
PAN, each salary slip, and the bank statement (minus whichever supplied the
Golden Record name — see section 3).

- Scored by similarity, **0 to 100**, passing at **85 or above**
- Word order does not matter: "Iyer Arjun Ramesh" still matches
- Missing or extra middle names are tolerated
- Initials are understood: **"Arjun R Iyer" matches "Arjun Ramesh Iyer"**
- But a *contradicting* initial is not forgiven: "Arjun P Iyer" against
  "Arjun Ramesh Iyer" scores low, because P and Ramesh genuinely conflict

**To pass:** the same person's name on every document, allowing for
abbreviation and spelling variation.

### 5.2 DOB — weight 0.10

Your date of birth appears on both Aadhaar and PAN, which makes it one of
only two facts that two documents can genuinely disagree about.

- Exact match after date normalisation: **100**
- Mismatch: **0** (reason `dob_differs`)
- Format differences are not mismatches — `19/08/1994` and `19-Aug-1994`
  are the same date

**To pass:** the date of birth on your PAN must equal the one on your
Aadhaar.

If your PAN's date of birth could not be read, this check simply does not
run. It counts neither for nor against you — see section 6, step 3.

### 5.3 SALARY_DATE — a gate, not a score

For **each** salary slip, the system looks for the matching credit in your
bank statement. A transaction qualifies only if **all** of these hold:

1. **It is a credit** — money in, not out.
2. **It falls inside the payment window.** Employers pay on different days,
   so the window is generous: from **5 days before** the salary month begins
   through **the end of the following month**. A March slip therefore
   accepts credits dated 24 February to 30 April.
3. **The amount is within 3% of the declared net salary.** For a declared
   ₹88,000, that is roughly ₹85,360 to ₹90,640.
4. **It has not already been claimed** by another slip.

Among the transactions that qualify, the best is chosen by blending:

```
   70%  how well the narration matches your employer's name
 + 30%  how close the amount is to the declared salary
```

and that best candidate must still score **60 or above** to be accepted.

**Why the 3% amount rule is a hard gate.** A bonus or reimbursement from the
same employer would score highly on narration alone. If narration could
outvote the amount, such a payment could stand in for a salary credit you
never actually received. Requiring the amount to be right *first* prevents
that.

This check carries no weight of its own. Instead it determines the two
checks below, which together carry 0.35.

### 5.4 EMPLOYER — weight 0.10

Each slip's employer name is compared to the narration of **its own**
matched credit.

- Similarity **0 to 100**, passing at **80 or above**
- `Infosys Limited` against `INFOSYS LIMITED SALARY MAR` scores very high
- If the slip found no matching credit, this scores **0**

**Changing jobs does not hurt you.** Each month is judged only against its
own bank credit — March's employer is never compared to June's. A job change
mid-history is normal and is not penalised.

### 5.5 SALARY_CREDIT_COUNT — weight 0.25, the heaviest check

The simplest check, and the one that moves your score most:

```
score = (slips with a matching credit ÷ total slips) × 100
```

Three slips, all matched → 100. Two of three → 66.7. One of three → 33.3.

**To pass:** every salary slip you submit should have a matching credit in
the bank statement. Because this carries the most weight, it is in practice
the check that decides most cases.

### 5.6 SALARY_CONTINUITY — weight 0.10

This one appears only when your bank statement covers a month you did not
submit a salary slip for. If your statement runs twelve months but you
supplied four slips, the eight remaining months are each listed here.

It is a statement about paperwork, not about your income. The system does
**not** try to guess what you earned in those months, and never treats a
neighbouring slip as evidence for them — a March slip proves March, and
nothing else.

**The month in progress does not count against you.** If your statement was
pulled part-way through a month, that final month is skipped: it is not over,
so your employer has not issued its slip yet. A statement ending 16 September
will not ask you for a September slip; one ending 30 September will.

**Scoring is all-or-nothing.** Every month listed scores 0, so one missing
month costs exactly what six do — about 14 points off an otherwise perfect
case. If your slips cover every completed month in your statement, this check
never runs and does not affect your score at all.

**To pass:** submit a slip for every complete month your bank statement
covers.

---

## 6. How the checks combine

**Step 1 — average within each check.** Four documents each producing a NAME
score become one NAME figure.

**Step 2 — apply the weights.**

| Check | Weight |
|-------|--------|
| SALARY_CREDIT_COUNT | 0.25 |
| NAME | 0.15 |
| DOB | 0.10 |
| EMPLOYER | 0.10 |
| SALARY_CONTINUITY | 0.10 |

**Step 3 — divide by the weight of the checks that actually ran.**

This last step matters. The weights are not percentages of a fixed total;
they are ratios to each other. If a check did not run — no months missing a slip, or no
readable date of birth on your PAN — its weight is removed from the divisor
too. You are never penalised for a check that had no reason to run, and no
check is allowed to contribute a free pass.

**Only checks that can genuinely fail carry weight.** Your Aadhaar and PAN
numbers each appear on exactly one document, so there is nothing to compare
them against. They must be *present* (section 4.2), but they are not scored.

---

## 7. Worked examples

All three use the same applicant: Arjun Ramesh Iyer, three monthly slips of
₹88,000 from Infosys Limited, and a bank statement showing three matching
credits.

### Example A — everything agrees

```
NAME                 100.0  x 0.15 =  15.00
DOB                  100.0  x 0.10 =  10.00
EMPLOYER             100.0  x 0.10 =  10.00
SALARY_CREDIT_COUNT  100.0  x 0.25 =  25.00
                             total =  60.00

                    60.00 / 0.60 = 100.00
```

**Result: PASS (100.00)**

SALARY_CONTINUITY never ran — the slips cover the statement — so its 0.10
was left out of the divisor. That is why the divisor is 0.60 and not 0.70.

### Example B — the PAN's date of birth disagrees

Everything else is unchanged; only the PAN shows a different date of birth.

```
NAME                 100.0  x 0.15 =  15.00
DOB                    0.0  x 0.10 =   0.00
EMPLOYER             100.0  x 0.10 =  10.00
SALARY_CREDIT_COUNT  100.0  x 0.25 =  25.00
                             total =  50.00

                    50.00 / 0.60 =  83.33
```

**Result: NEEDS_REVIEW (83.33)** — reason `DOB:dob_differs`

A perfect income history does not carry a contradicted identity through.

### Example C — two salary credits are missing

The slips are unchanged, but only one of the three expected credits appears
in the bank statement at the right amount.

```
NAME                 100.0  x 0.15 =  15.00
DOB                  100.0  x 0.10 =  10.00
EMPLOYER              33.3  x 0.10 =   3.33
SALARY_CREDIT_COUNT   33.3  x 0.25 =   8.33
                             total =  36.67

                    36.67 / 0.60 =  61.11
```

**Result: NEEDS_REVIEW (61.11)** — barely above the FAIL line

Notice the missing credits are counted twice over: once directly in
SALARY_CREDIT_COUNT, and again in EMPLOYER, because a slip with no matched
credit has no narration to verify its employer against.

---

## 8. Checklist to pass

Everything here should hold for a clean **PASS**.

**Documents**

- [ ] Aadhaar card submitted
- [ ] PAN card submitted
- [ ] At least one salary slip submitted
- [ ] Bank statement submitted

**Identity fields readable**

- [ ] Name legible on the Aadhaar or PAN
- [ ] Aadhaar number legible (masked, like `XXXX XXXX 7841`, is acceptable)
- [ ] PAN number legible
- [ ] Date of birth legible on the Aadhaar or PAN

**Identity agrees across documents**

- [ ] The same name on all four documents, allowing abbreviations and
      initials (similarity 85+)
- [ ] The date of birth on the PAN matches the one on the Aadhaar

**Income story holds**

- [ ] Every salary slip states an employer, a net salary and a salary month
- [ ] The bank statement covers the months the slips claim
- [ ] Each slip has a credit within **3%** of its declared net salary
- [ ] Each such credit falls within its window: 5 days before the salary
      month through the end of the following month
- [ ] Each credit's narration names the employer (similarity 80+)
- [ ] Distinct credits for distinct months — one credit cannot serve two
      slips
- [ ] Months between slips, up to the end of the statement, show salary
      credits of their own

**Formatting**

- [ ] Dates written unambiguously — four-digit years
- [ ] Amounts as plain figures; currency symbols and separators are fine

**The practical bar.** Identity checks tolerate a fair amount of fuzziness —
a name scoring 85 still passes comfortably. The income checks do not. Because
SALARY_CREDIT_COUNT and EMPLOYER together carry 0.35, **a single unmatched
salary slip out of three is enough to drop a case from PASS into
NEEDS_REVIEW**. If a slip's credit is genuinely absent from the statement,
expect review.

---

## 9. Reasons you may see

| Reason | Meaning |
|--------|---------|
| `MISSING_DOCUMENT:<TYPE>` | One of the four required documents was not submitted |
| `MANDATORY_FIELD_MISSING:<FIELD>` | Name, Aadhaar number, PAN number or DOB is absent from the merged profile |
| `NAME:name_below_threshold` | A document's name is too different from the others |
| `DOB:dob_differs` | The PAN and Aadhaar dates of birth do not match |
| `SALARY_DATE:no_matching_credit_in_window` | No qualifying credit was found for a slip |
| `SALARY_DATE:missing_salary_month` | A slip did not state which month it covers |
| `SALARY_DATE:missing_net_salary` | A slip did not state a net salary |
| `EMPLOYER:employer_narration_mismatch` | The credit's narration does not name the slip's employer |
| `EMPLOYER:no_matching_credit_to_verify_employer_against` | The slip had no matched credit, so its employer could not be checked |
| `EMPLOYER:missing_employer_name` | A slip did not state an employer |
| `SALARY_CREDIT_COUNT:below_threshold` | Not every slip found a matching credit |
| `SALARY_CONTINUITY:no_salary_slip_for_month` | Your statement covers a complete month you submitted no salary slip for |
| `score_meets_pass_threshold` | Passed on score |
| `score_below_fail_threshold` | Failed on score |

---

## 10. Settings reference

Every threshold is configurable. These are the current values.

| Setting | Value | Controls |
|---------|-------|----------|
| `NAME_MATCH_THRESHOLD` | 85.0 | Minimum name similarity to pass |
| `EMPLOYER_MATCH_THRESHOLD` | 80.0 | Minimum employer similarity to pass |
| `SALARY_AMOUNT_TOLERANCE_PCT` | 3.0 | How far a credit may differ from the declared salary |
| `SALARY_CREDIT_BUFFER_DAYS` | 5 | Days the payment window opens before the salary month |
| `SALARY_CREDIT_EXTRA_MONTHS` | 1 | Extra months the window stays open past the salary month |
| `TXN_SELECTION_EMPLOYER_WEIGHT` | 0.70 | Narration's share when picking the best credit |
| `TXN_SELECTION_AMOUNT_WEIGHT` | 0.30 | Amount's share when picking the best credit |
| `TXN_SELECTION_MIN_SCORE` | 60.0 | Minimum blended score for a credit to be accepted |
| `DECISION_PASS_THRESHOLD` | 90.0 | Score at or above which a case passes |
| `DECISION_FAIL_THRESHOLD` | 60.0 | Score below which a case fails |
