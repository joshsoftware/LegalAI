import axios from 'axios'
import { env } from '@/config/env'
import { toAppError } from '@/lib/errors'

// Slow work (OCR, translation, field mapping) runs in background workers and
// is polled, and the remaining slow calls set their own timeout, so this
// only covers quick requests.
const DEFAULT_TIMEOUT_MS = 30 * 1000

export const apiClient = axios.create({
  baseURL: env.VITE_API_BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Normalize all errors to a user-friendly AppError shape before they
    // reach hooks/pages. Never leak raw axios/stack details to the UI.
    return Promise.reject(toAppError(error))
  }
)

/**
 * Separate client for the translation microservice. As of the single-gateway
 * backend, VITE_TRANSLATION_API_BASE_URL points at the same gateway as
 * VITE_API_BASE_URL (which now fronts OCR, translation, and field-mapping
 * behind one port) — kept as its own client/env var in case translation is
 * ever split back onto its own host:port.
 */
export const translationApiClient = axios.create({
  baseURL: env.VITE_TRANSLATION_API_BASE_URL,
  timeout: DEFAULT_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
})

translationApiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    return Promise.reject(toAppError(error))
  }
)
