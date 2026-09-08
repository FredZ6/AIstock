'use server'

import type { ResearchRunActionState } from '../../lib/research-run-action-state'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { createResearchRun, LiveDataApiError } from '../../lib/server/live-data-api'

const symbolPattern = /^[A-Z.]{1,10}$/

function normalized(value: FormDataEntryValue | null): string {
  return typeof value === 'string' ? value.trim().toUpperCase() : ''
}

function text(value: FormDataEntryValue | null): string {
  return typeof value === 'string' ? value.trim() : ''
}

function failure(symbol: string, message: string): ResearchRunActionState {
  return { message, runId: null, status: 'error', symbol }
}

export async function startResearchRunAction(
  _previousState: ResearchRunActionState,
  formData: FormData,
): Promise<ResearchRunActionState> {
  const symbol = normalized(formData.get('symbol'))
  const idempotencyKey = text(formData.get('idempotency_key'))
  if (!symbolPattern.test(symbol)) {
    return failure(symbol, 'Symbol must match [A-Z.]{1,10}')
  }
  if (!idempotencyKey) {
    return failure(symbol, 'Research run requires an idempotency key.')
  }

  try {
    const config = readWebDataConfig(process.env)
    if (config.mode !== 'api') {
      return failure(symbol, 'Research runs require API mode.')
    }
    const decisionTime = new Date().toISOString()
    const run = await createResearchRun(
      { baseUrl: config.baseUrl, decisionTime },
      symbol,
      idempotencyKey,
    )
    return {
      message: 'Deterministic research run queued.',
      runId: run.runId,
      status: 'success',
      symbol,
    }
  } catch (error) {
    if (error instanceof LiveDataApiError && error.status === 429) {
      return failure(symbol, 'Research capacity is busy. Try again shortly.')
    }
    return failure(symbol, 'Unable to start research. Try again.')
  }
}
