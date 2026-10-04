import { translationApiClient } from './client'
import { pollTask } from './tasks'
import { taskSubmitResponseSchema } from '@/schemas/task.schema'
import { translationResponseSchema, type TranslationResult } from '@/schemas/translation.schema'

// POST /translate/text only validates and queues the request (the LLM call
// runs in a background worker), so it replies quickly.
const TRANSLATE_SUBMIT_TIMEOUT_MS = 30 * 1000

// Safety net only: the worker's Ollama read timeout (OLLAMA_TIMEOUT_SECONDS)
// is the real limit. This catches a worker that dies mid-task.
const TRANSLATE_MAX_PROCESSING_MS = 30 * 60 * 1000

/**
 * Translates a block of OCR-extracted text via the translation microservice:
 * queues the translation, then waits for the background job to finish.
 * Domain is always "banking" for this app — not configurable per document.
 * Only extraction.text should ever be passed here, never extraction.html.
 */
export async function translateText(text: string): Promise<TranslationResult> {
  const response = await translationApiClient.post(
    '/translate/text',
    { text, domain: 'banking' },
    { timeout: TRANSLATE_SUBMIT_TIMEOUT_MS }
  )
  const { task_id } = taskSubmitResponseSchema.parse(response.data)

  const result = await pollTask(task_id, { maxProcessingMs: TRANSLATE_MAX_PROCESSING_MS })
  return translationResponseSchema.parse(result).result
}
