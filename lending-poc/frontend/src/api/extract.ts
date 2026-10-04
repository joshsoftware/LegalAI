import { apiClient } from './client'
<<<<<<< HEAD
import { env } from '@/config/env'
=======
import { pollTask } from './tasks'
>>>>>>> chore/add-celery
import { extractResponseSchema, type ExtractResponse } from '@/schemas/extract.schema'
import { taskSubmitResponseSchema } from '@/schemas/task.schema'

<<<<<<< HEAD
// OCR extraction is CPU-bound and can take well over the client's default
// timeout, especially for multi-page documents or several concurrent
// uploads (the backend also serializes concurrent extractions, so later
// documents in a batch wait on earlier ones). CPU-only Surya can take
// several minutes per handwritten page, so this must stay aligned with the
// gateway's OCR_REQUEST_TIMEOUT_SECONDS default.
=======
// POST /extract only uploads the file and queues it (the OCR itself runs in
// a background worker), so this just needs to cover a max-size (50MB) upload.
const UPLOAD_TIMEOUT_MS = 2 * 60 * 1000

// Safety net only: the OCR worker enforces the real limit
// (OCR_TASK_TIME_LIMIT_SECONDS). This catches a worker that dies mid-task.
const EXTRACT_MAX_PROCESSING_MS = 30 * 60 * 1000

>>>>>>> chore/add-celery
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
<<<<<<< HEAD
    timeout: env.VITE_EXTRACT_TIMEOUT_MS,
=======
    timeout: UPLOAD_TIMEOUT_MS,
>>>>>>> chore/add-celery
  })
  const { task_id } = taskSubmitResponseSchema.parse(response.data)

  const result = await pollTask(task_id, { maxProcessingMs: EXTRACT_MAX_PROCESSING_MS })
  return extractResponseSchema.parse(result)
}
