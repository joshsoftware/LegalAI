import { apiClient } from './client'
import {
  fieldMappingResultSchema,
  type FieldMappingResult,
  type FieldMappingTemplateEntry,
} from '@/schemas/fieldMapping.schema'

export interface MapFieldsInput {
  /** This single document's translated (or OCR) text. */
  text: string
  /** This document's own template entry — one document per call, not the full template array. */
  template: FieldMappingTemplateEntry | unknown
}

// The backend calls out to a local LLM (Ollama) per request, which can run
// well past the client's default timeout under load or for longer text.
// TEMP(slow-host testing): raised from 5min to 30min. Revert before merging.
const MAP_FIELDS_TIMEOUT_MS = 30 * 60 * 1000

/**
 * Calls the field-mapping API for a single document. The backend
 * (field_mapping_poc/api.py) accepts { ocr_text, json_format } — json_format
 * being the target schema encoded as a JSON string — one document at a time,
 * so this is invoked once per document (see useFieldMapping), mirroring how
 * OCR and translation each run per document.
 */
export async function mapFields(input: MapFieldsInput): Promise<FieldMappingResult> {
  const response = await apiClient.post(
    '/map',
    {
      ocr_text: input.text,
      json_format: JSON.stringify(input.template),
    },
    { timeout: MAP_FIELDS_TIMEOUT_MS }
  )

  return fieldMappingResultSchema.parse(response.data)
}
