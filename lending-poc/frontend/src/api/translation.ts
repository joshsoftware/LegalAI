import { translationApiClient } from './client'
import { translationResponseSchema, type TranslationResult } from '@/schemas/translation.schema'

// The backend calls out to a local LLM per request, and (per the module's
// own docs) serves one generation at a time — later documents in a batch
// wait on earlier ones, well past the client's default timeout.
// TEMP(slow-host testing): raised from 5min to 30min. Revert before merging.
const TRANSLATE_TIMEOUT_MS = 30 * 60 * 1000

/**
 * Translates a block of OCR-extracted text via the translation microservice.
 * Domain is always "banking" for this app — not configurable per document.
 * Only extraction.text should ever be passed here, never extraction.html.
 */
export async function translateText(text: string): Promise<TranslationResult> {
  const response = await translationApiClient.post(
    '/translate/text',
    { text, domain: 'banking' },
    { timeout: TRANSLATE_TIMEOUT_MS }
  )

  return translationResponseSchema.parse(response.data).result
}
