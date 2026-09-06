import { NextRequest } from 'next/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GET } from '../app/api/research-runs/[runId]/events/route'

const runId = '01991f2b-2bb4-7db1-8890-5ff287e11bb2'
const originalEnvironment = { ...process.env }

describe('same-origin research run event proxy', () => {
  beforeEach(() => {
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://backend.internal:8000'
  })

  afterEach(() => {
    process.env = { ...originalEnvironment }
    vi.unstubAllGlobals()
  })

  it('rejects invalid run ids before contacting the backend', async () => {
    const upstream = vi.fn()
    vi.stubGlobal('fetch', upstream)

    const response = await GET(new NextRequest('http://localhost/api/research-runs/not-a-uuid/events'), {
      params: Promise.resolve({ runId: 'not-a-uuid' }),
    })

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({ error: 'Research run id must be a UUID' })
    expect(upstream).not.toHaveBeenCalled()
  })

  it('streams the server-only backend response and forwards the reconnect cursor', async () => {
    const upstream = vi.fn().mockResolvedValue(
      new Response('id: event-002\nevent: node.completed\ndata: {}\n\n', {
        headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      }),
    )
    vi.stubGlobal('fetch', upstream)

    const response = await GET(
      new NextRequest(`http://localhost/api/research-runs/${runId}/events`, {
        headers: { 'Last-Event-ID': 'event-001' },
      }),
      { params: Promise.resolve({ runId }) },
    )

    expect(upstream).toHaveBeenCalledWith(
      `http://backend.internal:8000/api/v1/events?run_id=${runId}`,
      expect.objectContaining({
        cache: 'no-store',
        headers: { Accept: 'text/event-stream', 'Last-Event-ID': 'event-001' },
      }),
    )
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toBe('text/event-stream; charset=utf-8')
    expect(response.headers.get('cache-control')).toBe('no-cache, no-transform')
    expect(response.headers.get('x-accel-buffering')).toBe('no')
    await expect(response.text()).resolves.toContain('id: event-002')
  })

  it('returns an explicit failure when API mode or the upstream stream is unavailable', async () => {
    process.env.WEB_DATA_MODE = 'fixture'
    vi.stubGlobal('fetch', vi.fn())

    const fixtureResponse = await GET(
      new NextRequest(`http://localhost/api/research-runs/${runId}/events`),
      { params: Promise.resolve({ runId }) },
    )
    expect(fixtureResponse.status).toBe(503)
    await expect(fixtureResponse.json()).resolves.toEqual({
      error: 'Live agent events require API mode; Fixture data was not substituted',
    })

    process.env.WEB_DATA_MODE = 'api'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('backend unavailable', { status: 503 })))
    const failedResponse = await GET(
      new NextRequest(`http://localhost/api/research-runs/${runId}/events`),
      { params: Promise.resolve({ runId }) },
    )
    expect(failedResponse.status).toBe(502)
    await expect(failedResponse.json()).resolves.toEqual({
      error: 'Agent event stream unavailable; Fixture data was not substituted',
    })
  })
})
