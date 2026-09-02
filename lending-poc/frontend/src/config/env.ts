import { z } from 'zod'


const envSchema = z.object({
  VITE_API_BASE_URL: z.string().url().or(z.string().startsWith('/')),
  VITE_TRANSLATION_API_BASE_URL: z.string().url().or(z.string().startsWith('/')),
})

export const env = envSchema.parse({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_TRANSLATION_API_BASE_URL: import.meta.env.VITE_TRANSLATION_API_BASE_URL,
})
