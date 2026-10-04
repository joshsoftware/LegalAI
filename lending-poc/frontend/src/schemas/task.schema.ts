import { z } from 'zod'

/**
 * Response to a request that queues a background task (e.g. POST /extract):
 * the backend replies 202 straight away with the id to poll.
 */
export const taskSubmitResponseSchema = z.object({
  task_id: z.string(),
})

/**
 * Response shape for GET /tasks/{task_id} on the gateway.
 * status is PENDING | STARTED | SUCCESS | FAILURE (Celery states), kept as a
 * plain string so any other state Celery reports doesn't fail parsing.
 * `result` is only set on SUCCESS and `error` only on FAILURE.
 */
export const taskStatusSchema = z.object({
  task_id: z.string(),
  status: z.string(),
  result: z.unknown().optional(),
  error: z.string().optional(),
})

export type TaskStatus = z.infer<typeof taskStatusSchema>
