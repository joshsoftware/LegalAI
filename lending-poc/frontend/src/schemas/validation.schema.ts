import { z } from 'zod'

// --- Request schema (mirrors app/schemas/case.py CaseCreateRequest) ---

export const bankTransactionInSchema = z.object({
  narration: z.string().nullable().optional(),
  // Strings are allowed for the same reason as net_salary below: field
  // mapping returns amounts as printed ("75,000"), and the backend
  // normalizes them. Dropping them here would lose the transaction silently.
  amount: z.union([z.number(), z.string()]).nullable().optional(),
  date: z.string().nullable().optional(),
})

export const aadhaarFieldsInSchema = z.object({
  name: z.string().nullable().optional(),
  address: z.string().nullable().optional(),
  // An all-digit Aadhaar number may come back unquoted from field mapping.
  aadhaar_number: z.union([z.string(), z.number()]).nullable().optional(),
  date_of_birth: z.string().nullable().optional(),
})

export const panFieldsInSchema = z.object({
  name: z.string().nullable().optional(),
  pan_number: z.string().nullable().optional(),
  date_of_birth: z.string().nullable().optional(),
})

export const salarySlipFieldsInSchema = z.object({
  name: z.string().nullable().optional(),
  employer_name: z.string().nullable().optional(),
  net_salary: z.union([z.number(), z.string()]).nullable().optional(),
  salary_month: z.string().nullable().optional(),
})

export const bankStatementFieldsInSchema = z.object({
  name: z.string().nullable().optional(),
  transactions: z.array(bankTransactionInSchema).default([]),
})

export const salarySlipInSchema = z.object({
  extracted_fields: salarySlipFieldsInSchema,
  source_file_ref: z.string().nullable().optional(),
})

export const aadhaarDocumentInSchema = z.object({
  doc_type: z.literal('AADHAAR'),
  extracted_fields: aadhaarFieldsInSchema,
  source_file_ref: z.string().nullable().optional(),
})

export const panDocumentInSchema = z.object({
  doc_type: z.literal('PAN'),
  extracted_fields: panFieldsInSchema,
  source_file_ref: z.string().nullable().optional(),
})

export const salarySlipDocumentInSchema = z.object({
  doc_type: z.literal('SALARY_SLIP'),
  salary_slips: z.array(salarySlipInSchema),
  source_file_ref: z.string().nullable().optional(),
})

export const bankStatementDocumentInSchema = z.object({
  doc_type: z.literal('BANK_STATEMENT'),
  extracted_fields: bankStatementFieldsInSchema,
  source_file_ref: z.string().nullable().optional(),
})

export const documentInSchema = z.discriminatedUnion('doc_type', [
  aadhaarDocumentInSchema,
  panDocumentInSchema,
  salarySlipDocumentInSchema,
  bankStatementDocumentInSchema,
])

export const caseCreateRequestSchema = z.object({
  applicant_ref: z.string(),
  documents: z.array(documentInSchema),
})

export type BankTransactionIn = z.infer<typeof bankTransactionInSchema>
export type AadhaarDocumentIn = z.infer<typeof aadhaarDocumentInSchema>
export type PanDocumentIn = z.infer<typeof panDocumentInSchema>
export type SalarySlipDocumentIn = z.infer<typeof salarySlipDocumentInSchema>
export type BankStatementDocumentIn = z.infer<typeof bankStatementDocumentInSchema>
export type DocumentIn = z.infer<typeof documentInSchema>
export type CaseCreateRequest = z.infer<typeof caseCreateRequestSchema>

// --- Response schema (mirrors CaseCreateResponse) ---

export const validationResultOutSchema = z.object({
  check_type: z.string(),
  passed: z.boolean(),
  score: z.number(),
  document_id: z.string().nullable().optional(),
  // evidence is dynamic/open-ended — shape varies by check_type.
  evidence: z.record(z.string(), z.unknown()).nullable().optional(),
})

export const caseCreateResponseSchema = z.object({
  case_id: z.string(),
  applicant_ref: z.string(),
  decision: z.string(),
  overall_score: z.number(),
  reasons: z.array(z.string()),
  validation_results: z.array(validationResultOutSchema),
})

export type ValidationResultOut = z.infer<typeof validationResultOutSchema>
export type CaseCreateResponse = z.infer<typeof caseCreateResponseSchema>
