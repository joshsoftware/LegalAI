import { apiClient } from './client'
import {
  caseCreateRequestSchema,
  caseCreateResponseSchema,
  type CaseCreateRequest,
  type CaseCreateResponse,
} from '@/schemas/validation.schema'

/**
 * Submits a case for validation against POST /cases.
 */
export async function createCase(payload: CaseCreateRequest): Promise<CaseCreateResponse> {
  // Validate on the way out too, not just the way back: the payload is built
  // from untyped field-mapping JSON, so a mapper regression is otherwise only
  // discoverable as an opaque 422 from the server. Use the parsed result —
  // zod returns a new object with unknown keys stripped.
  const body = caseCreateRequestSchema.parse(payload)
  const response = await apiClient.post('/cases', body)
  return caseCreateResponseSchema.parse(response.data)
}
