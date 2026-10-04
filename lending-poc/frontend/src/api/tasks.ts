import { apiClient } from './client'
import { taskStatusSchema, type TaskStatus } from '@/schemas/task.schema'

const POLL_INTERVAL_MS = 2000

// Each poll is a quick Redis read on the gateway, so a slow one means
// something is wrong — don't let it hang for the client's long default.
const POLL_REQUEST_TIMEOUT_MS = 15 * 1000

// A brief blip (network hiccup, gateway restart) shouldn't fail a document
// the worker is still happily processing — only give up after this many
// polls in a row fail.
const MAX_CONSECUTIVE_POLL_FAILURES = 5

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function fetchTaskStatus(taskId: string): Promise<TaskStatus | null> {
  try {
    const response = await apiClient.get(`/tasks/${taskId}`, { timeout: POLL_REQUEST_TIMEOUT_MS })
    return taskStatusSchema.parse(response.data)
  } catch {
    return null
  }
}

interface PollTaskOptions {
  /**
   * Give up if the task is still running this long after a worker started
   * it. Time spent waiting in the queue (PENDING) deliberately doesn't count,
   * so documents queued behind others in a batch can't time out just for
   * waiting their turn.
   */
  maxProcessingMs: number
}

/**
 * Polls GET /tasks/{taskId} until a background task finishes. Resolves with
 * the task's result on SUCCESS (callers validate it with their own schema);
 * throws on FAILURE, after too many failed polls, or if processing runs past
 * maxProcessingMs. Giving up here doesn't stop the task on the server.
 */
export async function pollTask(
  taskId: string,
  { maxProcessingMs }: PollTaskOptions
): Promise<unknown> {
  let startedAt: number | null = null
  let consecutiveFailures = 0

  for (;;) {
    const task = await fetchTaskStatus(taskId)

    if (task === null) {
      consecutiveFailures++
      if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
        throw new Error(
          'Lost contact with the server while waiting for the result. Please try again.'
        )
      }
    } else {
      consecutiveFailures = 0

      if (task.status === 'SUCCESS') return task.result
      if (task.status === 'FAILURE') throw new Error(task.error ?? 'Processing failed.')

      if (task.status === 'STARTED' && startedAt === null) startedAt = Date.now()
      if (startedAt !== null && Date.now() - startedAt > maxProcessingMs) {
        throw new Error('Processing is taking longer than expected. Please try again.')
      }
    }

    await sleep(POLL_INTERVAL_MS)
  }
}
