# Banking Domain — Knowledge Base

Terminology knowledge base for translating Marathi banking and identity documents into English.

## Covered Document Types

| Document | KB entries | ID range |
|---|---|---|
| Bank Statement | 10 | bk_0001 – bk_0010 |
| Salary Slip | 10 | bk_0021 – bk_0030 |
| Cost Sheet | 10 | bk_0031 – bk_0040 |
| Aadhaar / PAN / Identity | 10 | bk_0041 – bk_0050 |

## Categories

| Category | Description |
|---|---|
| `bank_statement` | Account statement fields and headers |
| `transaction_type` | Credit, debit, transfer, withdrawal terms |
| `account_type` | Savings, current, FD |
| `salary_slip` | Earnings components (basic, HRA, DA) and deductions (PF, PT, TDS) |
| `cost_sheet` | Property cost breakdown fields for home loan processing |
| `identity_document` | Aadhaar, PAN, KYC-related terms |
| `financial_term` | General banking terms (balance, loan, EMI, interest) |
| `institution` | Bank types and regulatory bodies |
| `regulatory` | RBI/KYC compliance terms |

## Adding New Entries

Each line in `banking_kb.jsonl` is one JSON object following `schema.json`.

Required fields: `id`, `domain`, `category`, `marathi`, `transliteration`, `semantic_english`, `definition`

```json
{
  "id": "bk_0051",
  "domain": "banking",
  "category": "bank_statement",
  "marathi": "...",
  "transliteration": "...",
  "semantic_english": "...",
  "literal_gloss": "...",
  "definition": "...",
  "usage_example_mr": "...",
  "usage_example_en": "...",
  "common_mistranslation": "...",
  "register": "formal_banking",
  "cross_refs": [],
  "source": "...",
  "confidence": "standard_usage"
}
```

Rules:
- IDs must be stable — never renumber or reuse once published
- Always use `semantic_english` as the preferred rendering; `literal_gloss` is for reference only
- Set `confidence` to `needs_sme_review` for any entry not sourced from RBI/UIDAI/official glossaries
