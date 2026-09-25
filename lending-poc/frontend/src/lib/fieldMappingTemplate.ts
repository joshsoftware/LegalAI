import type { FieldMappingTemplate, FieldMappingTemplateEntry } from '@/schemas/fieldMapping.schema'
import type { DocType } from '@/store/useAppStore'

/**
 * Static field-mapping template. Always the same for every case; shown to
 * the user via JsonViewer and will eventually be part of the field-mapping
 * request payload once the backend contract is confirmed.
 */
export const FIELD_MAPPING_TEMPLATE: FieldMappingTemplate = [
  {
    document_type: 'salary_slip',
    // One entry per slip present in the upload, not per uploaded file.
    // Applicants submit several months as a single multi-page PDF, and field
    // mapping runs once per file — so a flat single-slip shape left the model
    // nowhere to put month 2 and silently dropped it. Same array-of-one-example
    // convention as `transactions` below, and it matches the /cases contract,
    // where SALARY_SLIP carries a `salary_slips` array (see docs/cases_api.md).
    slips: [
      {
        document_metadata: {
          document_date: 'date (YYYY-MM-DD)',
          period: {
            from: 'Mandatory, date (YYYY-MM-DD)',
            to: 'Mandatory, date (YYYY-MM-DD)',
          },
          currency: '',
        },
        employer: { name: 'Mandatory' },
        employee: {
          employee_id: '',
          name: 'Mandatory',
          bank_account_number: 'Mandatory',
          date_of_joining: 'May be imp',
          days_worked: 'May be imp',
        },
        earnings: {
          basic_per_month: null,
          gross_per_month: null,
          allowances_per_month: null,
          other: null,
        },
        deductions: {
          total: null,
          tax: null,
          retirement_contribution: null,
          other: null,
        },
        net_salary: {
          amount: 'Mandatory, number (no currency symbol or thousands separators)',
          currency: 'Mandatory',
          amount_in_words: '',
        },
      },
    ],
  },
  {
    document_type: 'bank_statement',
    document_metadata: {
      statement_period: { from: '', to: '' },
      currency: '',
    },
    account: {
      account_number: '',
      customer_id: '',
      account_holder_name: '',
      account_type: '',
      bank_name: '',
      branch_name: '',
      lien_amount: null,
    },
    transactions: [
      {
        transaction_date: 'date (YYYY-MM-DD)',
        // Was a real company name ("Josh Software"), which a model can copy
        // straight into its output — that then feeds employer-narration
        // matching during validation.
        description: 'string (transaction narration exactly as printed)',
        amount: 'number (positive magnitude; use direction for credit/debit)',
        currency: '',
        // Kept as a word rather than a sign because that is how statements
        // print it; the frontend mapper folds it into the amount's sign.
        direction: "'Credited' or 'Debited'",
        balance: null,
      },
    ],
    summary: {
      total_credits: null,
      total_debits: null,
      opening_balance: null,
      closing_balance: null,
    },
  },
  {
    document_type: 'aadhaar',
    name: 'Mandatory',
    date_of_birth: 'Mandatory, date (YYYY-MM-DD)',
    aadhaar_number: 'Mandatory',
    address: 'Mandatory',
  },
  {
    document_type: 'pan',
    name: 'Mandatory',
    date_of_birth: 'Mandatory, date (YYYY-MM-DD)',
    pan_number: 'Mandatory',
  },
]

/** Maps our internal DocType to the template's document_type key. */
const DOC_TYPE_TO_TEMPLATE_KEY: Record<DocType, FieldMappingTemplateEntry['document_type']> = {
  AADHAAR: 'aadhaar',
  PAN: 'pan',
  SALARY_SLIP: 'salary_slip',
  BANK_STATEMENT: 'bank_statement',
}

/**
 * Field Mapping is called once per document, so each document only needs its
 * own template entry — not the full 4-entry array.
 */
export function getFieldMappingTemplateFor(docType: DocType): FieldMappingTemplateEntry {
  const key = DOC_TYPE_TO_TEMPLATE_KEY[docType]
  const entry = FIELD_MAPPING_TEMPLATE.find((t) => t.document_type === key)
  if (!entry) {
    throw new Error(`No field-mapping template found for document type "${docType}"`)
  }
  return entry
}
