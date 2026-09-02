'use server'

import { revalidatePath } from 'next/cache'

import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { initializePortfolio } from '../../lib/server/live-data-api'
import { parseAwareInstant } from '../../lib/time'

export async function initializePortfolioAction(formData: FormData): Promise<void> {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode !== 'api') throw new TypeError('Portfolio initialization requires API mode')
    const effectiveAt = String(formData.get('effective_at') ?? '')
    const idempotencyKey = String(formData.get('idempotency_key') ?? '')
    parseAwareInstant(effectiveAt)
    if (!idempotencyKey) throw new TypeError('Portfolio initialization requires an idempotency key')
    await initializePortfolio(
      { baseUrl: config.baseUrl, decisionTime: effectiveAt },
      idempotencyKey,
    )
  } catch (error) {
    reportLiveDataFailure('/portfolio', 'portfolio-initialization', error)
    throw new Error('Paper portfolio initialization failed')
  }
  revalidatePath('/portfolio')
}
