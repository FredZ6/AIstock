import { describe, expect, it, vi } from 'vitest'

import { LiveDataApiError } from '../lib/server/live-data-api'
import { reportLiveDataFailure } from '../lib/server/live-data-diagnostics'

describe('live data route diagnostics', () => {
  it('logs typed route context and correlation without leaking the upstream message', () => {
    const error = new LiveDataApiError(
      'response',
      'private upstream body and credentials',
      503,
      '6a8f1711-1b75-4ff7-a2cb-f38ae1a03079',
    )
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    reportLiveDataFailure('/alerts', 'alerts', error)

    expect(spy).toHaveBeenCalledWith('live-data-route-failure', {
      correlationId: '6a8f1711-1b75-4ff7-a2cb-f38ae1a03079',
      domain: 'alerts',
      kind: 'response',
      route: '/alerts',
      status: 503,
    })
    expect(JSON.stringify(spy.mock.calls)).not.toContain('credentials')
    spy.mockRestore()
  })

  it('classifies unexpected failures without serializing the error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    reportLiveDataFailure('/portfolio', 'portfolio', new Error('secret detail'))

    expect(spy).toHaveBeenCalledWith('live-data-route-failure', {
      correlationId: undefined,
      domain: 'portfolio',
      kind: 'unexpected',
      route: '/portfolio',
      status: undefined,
    })
    expect(JSON.stringify(spy.mock.calls)).not.toContain('secret detail')
    spy.mockRestore()
  })
})
