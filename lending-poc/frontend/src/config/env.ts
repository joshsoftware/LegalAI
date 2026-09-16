import { z } from 'zod'


const envSchema = z.object({
  VITE_API_BASE_URL: z.string().url().or(z.string().startsWith('/')),
  VITE_TRANSLATION_API_BASE_URL: z.string().url().or(z.string().startsWith('/')),
  // Client-level axios default. Per-call timeouts below override this.
  VITE_DEFAULT_TIMEOUT_MS: z.coerce.number().positive().default(30 * 1000),
  // OCR (Surya, CPU-bound) can take several minutes per handwritten page.
  VITE_EXTRACT_TIMEOUT_MS: z.coerce.number().positive().default(5 * 60 * 1000),
  // Field-mapping calls a local LLM (Ollama) per request.
  VITE_MAP_FIELDS_TIMEOUT_MS: z.coerce.number().positive().default(5 * 60 * 1000),
  // Translation calls a local LLM (Ollama) per request.
  VITE_TRANSLATE_TIMEOUT_MS: z.coerce.number().positive().default(5 * 60 * 1000),
})

export const env = envSchema.parse({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_TRANSLATION_API_BASE_URL: import.meta.env.VITE_TRANSLATION_API_BASE_URL,
  VITE_DEFAULT_TIMEOUT_MS: import.meta.env.VITE_DEFAULT_TIMEOUT_MS,
  VITE_EXTRACT_TIMEOUT_MS: import.meta.env.VITE_EXTRACT_TIMEOUT_MS,
  VITE_MAP_FIELDS_TIMEOUT_MS: import.meta.env.VITE_MAP_FIELDS_TIMEOUT_MS,
  VITE_TRANSLATE_TIMEOUT_MS: import.meta.env.VITE_TRANSLATE_TIMEOUT_MS,
})
