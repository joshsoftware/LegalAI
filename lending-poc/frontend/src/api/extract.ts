import { apiClient } from './client'
import { extractResponseSchema, type ExtractResponse } from '@/schemas/extract.schema'

// OCR extraction is CPU-bound and can take well over the client's default
// 30s timeout, especially for multi-page documents or several concurrent
// uploads (the backend also serializes concurrent extractions, so later
// documents in a batch wait on earlier ones). CPU-only Surya can take
// several minutes per handwritten page, so this must stay aligned with the
// gateway's OCR_REQUEST_TIMEOUT_SECONDS default.
const EXTRACT_TIMEOUT_MS = 5 * 60 * 1000

/**
 * POSTs a single file to /extract. The backend processes one file per call,
 * and the multipart field name must be "file" (lowercase), matching the
 * `file: UploadFile` parameter name in document_processing/ocr/api.py.
 */
export async function extractOne(file: File): Promise<ExtractResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await apiClient.post('/extract', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: EXTRACT_TIMEOUT_MS,
  })

  return extractResponseSchema.parse(response.data)
}
