import 'server-only'

export function reportLiveDataFailure(route: string, domain: string, error: unknown): void {
  const candidate = typeof error === 'object' && error !== null
    ? error as { correlationId?: unknown; kind?: unknown; status?: unknown }
    : null
  const kind = candidate && ['contract', 'response', 'unavailable'].includes(String(candidate.kind))
    ? candidate.kind
    : 'unexpected'
  console.error('live-data-route-failure', {
    correlationId: typeof candidate?.correlationId === 'string' ? candidate.correlationId : undefined,
    domain,
    kind,
    route,
    status: typeof candidate?.status === 'number' ? candidate.status : undefined,
  })
}
