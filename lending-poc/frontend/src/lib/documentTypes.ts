import type { DocType } from '@/store/useAppStore'
import { env } from '@/config/env'

export interface DocTypeConfig {
  docType: DocType
  label: string
  group: 'Identity Documents' | 'Financial Documents'
}

export const DOCUMENT_TYPE_CONFIG: DocTypeConfig[] = [
  { docType: 'AADHAAR', label: 'Aadhaar', group: 'Identity Documents' },
  { docType: 'PAN', label: 'PAN', group: 'Identity Documents' },
  { docType: 'SALARY_SLIP', label: 'Salary Slip', group: 'Financial Documents' },
  { docType: 'BANK_STATEMENT', label: 'Bank Statement', group: 'Financial Documents' },
]

export const ACCEPTED_FILE_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
export const ACCEPTED_FILE_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg']
export const MAX_FILE_SIZE_MB = env.VITE_MAX_UPLOAD_FILE_SIZE_MB // matches backend MAX_UPLOAD_FILE_SIZE_MB
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

export function isAcceptedFileType(file: File): boolean {
  const name = file.name.toLowerCase()
  return (
    ACCEPTED_FILE_TYPES.includes(file.type) ||
    ACCEPTED_FILE_EXTENSIONS.some((ext) => name.endsWith(ext))
  )
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function docTypeLabel(docType: DocType): string {
  return DOCUMENT_TYPE_CONFIG.find((c) => c.docType === docType)?.label ?? docType
}
