import { NextRequest } from 'next/server'

import { readWebDataConfig } from '../../../../../lib/server/data-mode'

export const dynamic = 'force-dynamic'

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

type RouteContext = {
  params: Promise<{ runId: string }>
}

const failure = (error: string, status: number) => Response.json({ error }, { status })

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  const { runId } = await context.params
  if (!uuidPattern.test(runId)) return failure('Research run id must be a UUID', 400)

  const config = readWebDataConfig(process.env)
  if (config.mode !== 'api') {
    return failure('Live agent events require API mode; Fixture data was not substituted', 503)
  }

  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  const lastEventId = request.headers.get('Last-Event-ID')
  if (lastEventId) headers['Last-Event-ID'] = lastEventId

  let upstream: Response
  try {
    const url = new URL('/api/v1/events', config.baseUrl)
    url.searchParams.set('run_id', runId)
    upstream = await fetch(url.toString(), {
      cache: 'no-store',
      headers,
      signal: request.signal,
    })
  } catch {
    return failure('Agent event stream unavailable; Fixture data was not substituted', 502)
  }

  if (!upstream.ok || !upstream.body) {
    return failure('Agent event stream unavailable; Fixture data was not substituted', 502)
  }

  return new Response(upstream.body, {
    headers: {
      'Cache-Control': 'no-cache, no-transform',
      'Content-Type': upstream.headers.get('Content-Type') ?? 'text/event-stream',
      'X-Accel-Buffering': 'no',
    },
  })
}
