import { z } from 'zod'

/**
 * Result of one OCR job: what GET /tasks/{task_id} returns as `result` once
 * a POST /extract upload (one file per request) finishes processing.
 * NOTE: extraction.html is currently commented out on the backend and not
 * returned — keep it optional so the UI can fall back gracefully.
 */
export const extractResponseSchema = z.object({
  filename: z.string(),
  file_type: z.string(),
  pages_processed: z.number(),
  extraction: z.object({
    text: z.string(),
    html: z.string().optional(),
  }),
  metadata: z.object({
    processing_engine: z.string(),
  }),
})

export type ExtractResponse = z.infer<typeof extractResponseSchema>
