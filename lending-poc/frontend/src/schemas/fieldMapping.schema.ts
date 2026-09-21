import { z } from 'zod'

/**
 * The field-mapping backend contract is not yet finalized, so the result is
 * treated as arbitrary nested JSON keyed by document type. Once the real
 * contract lands, replace this with a properly typed schema.
 */
export const fieldMappingResultSchema = z.record(z.string(), z.unknown())

export type FieldMappingResult = z.infer<typeof fieldMappingResultSchema>

// --- Known, fully-specified template structure (static, not from the API) ---

export const salarySlipTemplateSchema = z.object({
  document_type: z.literal('salary_slip'),
  // An array because one upload can hold several months of slips — see the
  // comment on FIELD_MAPPING_TEMPLATE's salary_slip entry.
  slips: z.array(
    z.object({
      document_metadata: z.object({
        document_date: z.string(),
        period: z.object({ from: z.string(), to: z.string() }),
        currency: z.string(),
      }),
      employer: z.object({ name: z.string() }),
      employee: z.object({
        employee_id: z.string(),
        name: z.string(),
        bank_account_number: z.string(),
        date_of_joining: z.string(),
        days_worked: z.string(),
      }),
      earnings: z.object({
        basic_per_month: z.null(),
        gross_per_month: z.null(),
        allowances_per_month: z.null(),
        other: z.null(),
      }),
      deductions: z.object({
        total: z.null(),
        tax: z.null(),
        retirement_contribution: z.null(),
        other: z.null(),
      }),
      net_salary: z.object({
        amount: z.string(),
        currency: z.string(),
        amount_in_words: z.string(),
      }),
    })
  ),
})

export const bankStatementTemplateSchema = z.object({
  document_type: z.literal('bank_statement'),
  document_metadata: z.object({
    statement_period: z.object({ from: z.string(), to: z.string() }),
    currency: z.string(),
  }),
  account: z.object({
    account_number: z.string(),
    customer_id: z.string(),
    account_holder_name: z.string(),
    account_type: z.string(),
    bank_name: z.string(),
    branch_name: z.string(),
    lien_amount: z.null(),
  }),
  transactions: z.array(
    z.object({
      transaction_date: z.string(),
      description: z.string(),
      // A hint string, not a null placeholder — the model needs to be told
      // this is a plain number.
      amount: z.string(),
      currency: z.string(),
      direction: z.string(),
      balance: z.null(),
    })
  ),
  summary: z.object({
    total_credits: z.null(),
    total_debits: z.null(),
    opening_balance: z.null(),
    closing_balance: z.null(),
  }),
})

export const aadhaarTemplateSchema = z.object({
  document_type: z.literal('aadhaar'),
  name: z.string(),
  date_of_birth: z.string(),
  aadhaar_number: z.string(),
  address: z.string(),
})

export const panTemplateSchema = z.object({
  document_type: z.literal('pan'),
  name: z.string(),
  date_of_birth: z.string(),
  pan_number: z.string(),
})

export const fieldMappingTemplateSchema = z.array(
  z.union([
    salarySlipTemplateSchema,
    bankStatementTemplateSchema,
    aadhaarTemplateSchema,
    panTemplateSchema,
  ])
)

export type FieldMappingTemplate = z.infer<typeof fieldMappingTemplateSchema>
export type FieldMappingTemplateEntry = FieldMappingTemplate[number]
