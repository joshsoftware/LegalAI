import type {
  DocType,
  FieldMappingEntry,
  OcrEntry,
  TranslationEntry,
  UploadedDocument,
} from '@/store/useAppStore'
import type { CaseCreateResponse } from '@/schemas/validation.schema'
import type { FieldMappingResult } from '@/schemas/fieldMapping.schema'

/**
 * TEMPORARY: UI-only mock data so the full workflow (including Field Mapping
 * and Validation, which have no live backend yet) can be reviewed end-to-end
 * without running the OCR/translation/backend services.
 *
 * Remove this file and its call site (UploadPage's "Load Mock Data" button)
 * once real backends are wired up for every step.
 */

function makeMockFile(name: string, type: string): File {
  return new File(['mock file content'], name, { type })
}

const MOCK_OCR_HTML: Record<DocType, string> = {
  AADHAAR: `<h2>Government of India</h2><p><strong>Name:</strong> Sneha Sunil Lokhande</p><p><strong>DOB:</strong> 14/03/1995</p><p><strong>Aadhaar Number:</strong> 6446 7654 4321</p><p><strong>Address:</strong> Flat 204, Green Heights, Baner, Pune, Maharashtra 411045</p>`,
  PAN: `<h2>Income Tax Department</h2><p><strong>Name:</strong> Sneha Sunil Lokhande</p><p><strong>PAN:</strong> ABCPL1234F</p><p><strong>DOB:</strong> 14/03/1995</p>`,
  SALARY_SLIP: `<h2>ABC Technologies Pvt Ltd</h2><p>Payslip for March 2026</p><table border="1"><tr><td>Employee</td><td>Sneha Sunil Lokhande</td></tr><tr><td>Net Salary</td><td>INR 75,000</td></tr></table>`,
  BANK_STATEMENT: `<h2>State Bank</h2><p>Account Statement</p><table border="1"><tr><th>Date</th><th>Narration</th><th>Amount</th></tr><tr><td>2026-04-01</td><td>ABC Technologies Pvt Ltd Salary</td><td>+75,000</td></tr></table>`,
}

const MOCK_OCR_TEXT: Record<DocType, string> = {
  AADHAAR:
    'Government of India\nName: Sneha Sunil Lokhande\nDOB: 14/03/1995\nAadhaar Number: 6446 7654 4321\nAddress: Flat 204, Green Heights, Baner, Pune, Maharashtra 411045',
  PAN: 'Income Tax Department\nName: Sneha Sunil Lokhande\nPAN: ABCPL1234F\nDOB: 14/03/1995',
  SALARY_SLIP:
    'ABC Technologies Pvt Ltd\nPayslip for March 2026\nEmployee: Sneha Sunil Lokhande\nNet Salary: INR 75,000',
  BANK_STATEMENT:
    'State Bank\nAccount Statement\n2026-04-01 ABC Technologies Pvt Ltd Salary +75,000',
}

const MOCK_TRANSLATED_TEXT: Record<DocType, string> = {
  AADHAAR: MOCK_OCR_TEXT.AADHAAR,
  PAN: MOCK_OCR_TEXT.PAN,
  SALARY_SLIP: MOCK_OCR_TEXT.SALARY_SLIP,
  BANK_STATEMENT: MOCK_OCR_TEXT.BANK_STATEMENT,
}

const MOCK_FILE_META: Record<DocType, { name: string; type: string }> = {
  AADHAAR: { name: 'aadhaar_card.jpg', type: 'image/jpeg' },
  PAN: { name: 'pan_card.jpg', type: 'image/jpeg' },
  SALARY_SLIP: { name: 'salary_slip_march.pdf', type: 'application/pdf' },
  BANK_STATEMENT: { name: 'bank_statement.pdf', type: 'application/pdf' },
}

export function buildMockUploadedDocuments(): UploadedDocument[] {
  return (Object.keys(MOCK_FILE_META) as DocType[]).map((docType) => {
    const meta = MOCK_FILE_META[docType]
    const file = makeMockFile(meta.name, meta.type)
    return {
      id: `${docType}-${meta.name}-mock`,
      docType,
      file,
      fileName: meta.name,
      fileSize: file.size,
      fileType: meta.type,
    }
  })
}

export function buildMockOcrResults(documents: UploadedDocument[]): Record<string, OcrEntry> {
  const results: Record<string, OcrEntry> = {}
  documents.forEach((doc) => {
    results[doc.id] = {
      status: 'success',
      data: {
        filename: doc.fileName,
        file_type: `.${doc.fileName.split('.').pop()}`,
        pages_processed: 1,
        extraction: {
          text: MOCK_OCR_TEXT[doc.docType],
          html: MOCK_OCR_HTML[doc.docType],
        },
        metadata: { processing_engine: 'surya' },
      },
    }
  })
  return results
}

export function buildMockTranslationResults(
  documents: UploadedDocument[]
): Record<string, TranslationEntry> {
  const results: Record<string, TranslationEntry> = {}
  documents.forEach((doc) => {
    results[doc.id] = {
      status: 'success',
      data: {
        source: doc.fileName,
        domain: 'banking',
        translation: MOCK_TRANSLATED_TEXT[doc.docType],
        kb_matches: 2,
      },
    }
  })
  return results
}

// One field-mapping result per document, matching the per-document API call.
const MOCK_FIELD_MAPPING_RESULT_BY_DOC_TYPE: Record<DocType, FieldMappingResult> = {
  AADHAAR: {
    document_type: 'aadhaar',
    name: 'Sneha Sunil Lokhande',
    date_of_birth: '1995-03-14',
    aadhaar_number: '6446 7654 4321',
    address: 'Flat 204, Green Heights, Baner, Pune, Maharashtra 411045',
  },
  PAN: {
    document_type: 'pan',
    name: 'Sneha Sunil Lokhande',
    pan_number: 'ABCPL1234F',
  },
  SALARY_SLIP: {
    document_type: 'salary_slip',
    document_metadata: {
      document_date: '2026-03-31',
      period: { from: '2026-03-01', to: '2026-03-31' },
      currency: 'INR',
    },
    employer: { name: 'ABC Technologies Pvt Ltd' },
    employee: { name: 'Sneha Sunil Lokhande' },
    net_salary: { amount: 75000, currency: 'INR' },
  },
  BANK_STATEMENT: {
    document_type: 'bank_statement',
    account: {
      account_holder_name: 'Sneha Sunil Lokhande',
      account_number: 'XXXXXXXX1234',
    },
    transactions: [
      {
        transaction_date: '2026-04-01',
        description: 'ABC Technologies Pvt Ltd',
        amount: 75000,
        direction: 'Credited',
      },
    ],
  },
}

export function buildMockFieldMappingResults(
  documents: UploadedDocument[]
): Record<string, FieldMappingEntry> {
  const results: Record<string, FieldMappingEntry> = {}
  documents.forEach((doc) => {
    results[doc.id] = {
      status: 'success',
      data: MOCK_FIELD_MAPPING_RESULT_BY_DOC_TYPE[doc.docType],
    }
  })
  return results
}

export const MOCK_VALIDATION_RESULT: CaseCreateResponse = {
  case_id: 'a242f1d0-fd32-4f46-8864-8d4ac23cdcbf',
  applicant_ref: 'APP-2026-09194',
  decision: 'PASS',
  overall_score: 97.8,
  reasons: ['score_meets_pass_threshold'],
  validation_results: [
    {
      check_type: 'NAME',
      passed: true,
      score: 100.0,
      document_id: 'AADHAAR',
      evidence: {
        source_text: 'SNEHA SUNIL LOKHANDE',
        target_text: 'SNEHA SUNIL LOKHANDE',
        match_type: 'FUZZY',
      },
    },
    {
      check_type: 'AADHAAR',
      passed: true,
      score: 100.0,
      document_id: 'AADHAAR',
      evidence: {
        source_text: '6446 7654 4321',
        target_text: '6446 7654 4321',
        match_type: 'EXACT',
      },
    },
    {
      check_type: 'PAN',
      passed: true,
      score: 100.0,
      document_id: 'PAN',
      evidence: {
        source_text: 'ABCPL1234F',
        target_text: 'ABCPL1234F',
        match_type: 'EXACT',
      },
    },
    {
      check_type: 'DOB',
      passed: true,
      score: 100.0,
      document_id: 'AADHAAR',
      evidence: {
        source_text: '1995-03-14',
        target_text: '1995-03-14',
        match_type: 'EXACT',
      },
    },
    {
      check_type: 'SALARY_DATE',
      passed: true,
      score: 100.0,
      document_id: 'BANK_STATEMENT',
      evidence: {
        source_text: 'March 2026',
        target_text: '2026-03',
        match_type: 'DATE_MATCH',
        matched_transaction: {
          narration: 'ABC Technologies Pvt Ltd',
          amount: 75000,
          txn_date: '2026-04-01',
        },
      },
    },
    {
      check_type: 'EMPLOYER',
      passed: true,
      score: 80.0,
      document_id: 'SALARY_SLIP',
      evidence: {
        source_text: 'ABC Technologies Pvt Ltd',
        target_text: 'ABC Technologies Pvt Ltd',
        match_type: 'FUZZY',
      },
    },
    {
      check_type: 'SALARY_CREDIT_COUNT',
      passed: true,
      score: 100.0,
      document_id: 'BANK_STATEMENT',
      evidence: {
        source_value: 1,
        target_value: 1,
        match_type: 'COUNT_MATCH',
        stmt_duration: { start: '2026-04-01', end: '2026-04-01' },
        total_slips: 1,
        confidence_score: 100,
      },
    },
  ],
}
