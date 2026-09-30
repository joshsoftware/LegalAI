import { apiClient } from './client'
import { pollTask } from './tasks'
import { taskSubmitResponseSchema } from '@/schemas/task.schema'
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

// POST /map only validates and queues the request (the LLM call runs in a
// background worker), so it replies quickly.
const MAP_SUBMIT_TIMEOUT_MS = 30 * 1000

// Safety net only: the worker's Ollama read timeout (OLLAMA_TIMEOUT_SECONDS)
// is the real limit. This catches a worker that dies mid-task.
const MAP_FIELDS_MAX_PROCESSING_MS = 30 * 60 * 1000

/**
 * Queues field mapping for a single document, then waits for the background
 * job to finish. The backend (field_mapping_poc/api.py) accepts
 * { ocr_text, json_format } — json_format being the target schema encoded as
 * a JSON string — one document at a time, so this is invoked once per
 * document (see useFieldMapping), mirroring how OCR and translation each run
 * per document.
 */
export async function mapFields(input: MapFieldsInput): Promise<FieldMappingResult> {
  const response = await apiClient.post(
    '/map',
    {
      ocr_text: input.text,
      json_format: JSON.stringify(input.template),
    },
    { timeout: MAP_SUBMIT_TIMEOUT_MS }
  )
  const { task_id } = taskSubmitResponseSchema.parse(response.data)

  const result = await pollTask(task_id, { maxProcessingMs: MAP_FIELDS_MAX_PROCESSING_MS })
  return fieldMappingResultSchema.parse(result)
}
