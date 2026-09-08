'use client'

import { useRouter } from 'next/navigation'
import { useActionState, useEffect } from 'react'
import { useFormStatus } from 'react-dom'

import { startResearchRunAction } from '../../app/research/actions'
import { initialResearchRunActionState } from '../../lib/research-run-action-state'

function SubmitButton() {
  const { pending } = useFormStatus()
  return (
    <button disabled={pending} type="submit">
      {pending ? 'Queueing research…' : 'Run deterministic research'}
    </button>
  )
}

export function ResearchRunControl({
  idempotencyKey,
  symbol,
}: {
  idempotencyKey: string
  symbol: string
}) {
  const router = useRouter()
  const [state, action] = useActionState(
    startResearchRunAction,
    initialResearchRunActionState,
  )

  useEffect(() => {
    if (state.status === 'success' && state.runId) {
      router.push(`/runs/${state.runId}`)
    }
  }, [router, state.runId, state.status])

  return (
    <section className="research-run-control" aria-labelledby="research-run-title">
      <div>
        <p className="section-kicker">Deterministic Research Workflow</p>
        <h2 id="research-run-title">Start a persisted research run</h2>
        <p>Runs execute through the durable worker and preserve point-in-time evidence.</p>
      </div>
      <form action={action}>
        <label htmlFor="research-run-symbol">Research symbol</label>
        <input
          autoCapitalize="characters"
          defaultValue={symbol}
          id="research-run-symbol"
          maxLength={10}
          name="symbol"
          required
        />
        <input name="idempotency_key" type="hidden" value={idempotencyKey} />
        <SubmitButton />
      </form>
      {state.status !== 'idle' ? (
        <p
          className="research-run-message"
          data-status={state.status}
          role={state.status === 'error' ? 'alert' : 'status'}
        >
          {state.message}
        </p>
      ) : null}
    </section>
  )
}
