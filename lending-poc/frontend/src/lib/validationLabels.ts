// User-facing names for the raw ids the validation API returns.
// The API deliberately sends stable ids (check types, document ids) rather
// than display text, so wording can change here without touching the backend.

const CHECK_LABELS: Record<string, string> = {
  NAME: 'Name match',
  DOB: 'Date of birth match',
  AADHAAR: 'Aadhaar number present',
  PAN: 'PAN number present',
  ADDRESS: 'Address match',
  EMPLOYER: 'Employer verification',
  SALARY_DATE: 'Salary credited to bank',
  SALARY_CREDIT_COUNT: 'Salary credit coverage',
  SALARY_CONTINUITY: 'Missing salary slip',
  MANDATORY_PRESENCE: 'Required documents present',
}

// Keep in sync with doc_label in app/services/evidence_format.py, which
// uses the same names inside the backend-generated messages.
const DOCUMENT_LABELS: Record<string, string> = {
  AADHAAR: 'Aadhaar',
  PAN: 'PAN',
  BANK_STATEMENT: 'Bank Statement',
  SALARY_SLIPS: 'Salary Slips',
}

export function checkLabel(checkType: string): string {
  return CHECK_LABELS[checkType] ?? checkType
}

export function documentLabel(docId: string | null | undefined): string {
  if (!docId) return '—'
  if (DOCUMENT_LABELS[docId]) return DOCUMENT_LABELS[docId]
  // "SALARY_SLIP-0" -> "Salary Slip 1": slips are numbered from 1 for humans.
  const slip = /^SALARY_SLIP-(\d+)$/.exec(docId)
  if (slip) return `Salary Slip ${Number(slip[1]) + 1}`
  return docId
}
