import { describe, expect, it } from 'vitest'

import { DurableEventStore, reconnectRequest } from '../lib/sse'

const event = (overrides: Partial<Parameters<DurableEventStore['append']>[0]> = {}) => ({
  event_id: 'event-001',
  event_time: '2026-08-21T20:00:00Z',
  payload: { node: 'preflight' },
  run_id: 'run-001',
  schema_version: '1.0',
  sequence: 1,
  type: 'node.completed',
  ...overrides,
})

describe('durable SSE client state', () => {
  it('builds a reconnect request with the durable Last-Event-ID cursor', () => {
    expect(reconnectRequest('/api/v1/events', 'run-001', 'event-009')).toEqual({
      headers: { 'Last-Event-ID': 'event-009' },
      url: '/api/v1/events?run_id=run-001',
    })
  })

  it('suppresses redelivered event IDs and retains authoritative sequence order', () => {
    const store = new DurableEventStore('run-001')

    expect(store.append(event({ event_id: 'event-002', sequence: 2 }))).toBe(true)
    expect(store.append(event())).toBe(true)
    expect(store.append(event())).toBe(false)

    expect(store.events.map((item) => item.event_id)).toEqual(['event-001', 'event-002'])
    expect(store.lastEventId).toBe('event-002')
  })

  it('rejects cross-run events, naive timestamps, and sequence collisions', () => {
    const store = new DurableEventStore('run-001')
    store.append(event())

    expect(() => store.append(event({ event_id: 'event-other', run_id: 'run-002' }))).toThrow(
      /run mismatch/i,
    )
    expect(() => store.append(event({ event_id: 'event-naive', event_time: '2026-08-21T20:00:00' }))).toThrow(
      /timezone/i,
    )
    expect(() => store.append(event({ event_id: 'event-collision' }))).toThrow(/sequence collision/i)
  })
})
