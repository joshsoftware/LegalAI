import { apiClient } from './client'
import { pollTask } from './tasks'
import { extractResponseSchema, type ExtractResponse } from '@/schemas/extract.schema'
import { taskSubmitResponseSchema } from '@/schemas/task.schema'

// POST /extract only uploads the file and queues it (the OCR itself runs in
// a background worker), so this just needs to cover a max-size (50MB) upload.
const UPLOAD_TIMEOUT_MS = 2 * 60 * 1000

// How long OCR may run once a worker has started on this document.
// CPU-only Surya can take several minutes per handwritten page. Unlike the
// old single-request timeout, time spent queued behind other documents in
// the batch doesn't count against this.
// TEMP(slow-host testing): raised from 5min to 30min. Revert before merging.
const EXTRACT_MAX_PROCESSING_MS = 30 * 60 * 1000

/**
 * Uploads a single file to /extract, then waits for its background OCR job
 * to finish. The backend processes one file per call, and the multipart
 * field name must be "file" (lowercase), matching the `file: UploadFile`
 * parameter name in document_processing/ocr/api.py.
 */
export async function extractOne(file: File): Promise<ExtractResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await apiClient.post('/extract', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: UPLOAD_TIMEOUT_MS,
  })
  const { task_id } = taskSubmitResponseSchema.parse(response.data)

  const result = await pollTask(task_id, { maxProcessingMs: EXTRACT_MAX_PROCESSING_MS })
  return extractResponseSchema.parse(result)
}
