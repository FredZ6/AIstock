export type AvailabilityState =
  | 'EMPTY'
  | 'UNSUPPORTED'
  | 'UNCONFIGURED'
  | 'STALE'
  | 'DEGRADED'
  | 'FAILURE'

export type AvailabilityAction = {
  href: string
  label: string
}

export type AvailabilityFact = {
  action: AvailabilityAction | null
  key: string
  label: string
  reason: string
  state: AvailabilityState
}

type ProviderState = {
  configured: boolean
  coverage?: string | null
  mode: 'fixture' | 'read_only' | 'unavailable'
  operatorAction?: string | null
  status?: 'SUCCESS' | 'DEGRADED' | 'FAILURE' | 'UNAVAILABLE'
}

const priority: Record<AvailabilityState, number> = {
  EMPTY: 0,
  DEGRADED: 1,
  STALE: 2,
  UNSUPPORTED: 3,
  UNCONFIGURED: 4,
  FAILURE: 5,
}

function providerLabel(name: string): string {
  return name.replaceAll('_', ' ').toUpperCase()
}

function inferredState(reason: string): AvailabilityState {
  if (/unsupported|no approved|no .*producer exists/i.test(reason)) return 'UNSUPPORTED'
  if (/unconfigured|configure\b|missing credential/i.test(reason)) return 'UNCONFIGURED'
  if (/stale|freshness/i.test(reason)) return 'STALE'
  if (/degraded|coverage|quality|gap/i.test(reason)) return 'DEGRADED'
  if (/fail|invalid contract|request error/i.test(reason)) return 'FAILURE'
  return 'EMPTY'
}

export function availabilityFromDomain(input: {
  action?: AvailabilityAction | null
  key: string
  label: string
  reason: string
  state?: AvailabilityState
}): AvailabilityFact {
  return {
    action: input.action ?? null,
    key: input.key,
    label: input.label,
    reason: input.reason,
    state: input.state ?? inferredState(input.reason),
  }
}

export function availabilityFromProvider(name: string, provider: ProviderState): AvailabilityFact | null {
  const label = providerLabel(name)
  if (!provider.configured) {
    return availabilityFromDomain({
      key: `provider:${name}`,
      label,
      reason: provider.operatorAction ?? `Configure the approved read-only ${label} provider.`,
      state: 'UNCONFIGURED',
    })
  }
  if (provider.status === 'FAILURE') {
    return availabilityFromDomain({
      key: `provider:${name}`,
      label,
      reason: provider.operatorAction ?? `${label} ingestion or quality checks failed. Review runtime diagnostics.`,
      state: 'FAILURE',
      action: { href: '/eval', label: `Review ${label} runtime` },
    })
  }
  if (provider.status === 'DEGRADED') {
    return availabilityFromDomain({
      key: `provider:${name}`,
      label,
      reason: provider.operatorAction ?? `${label} is returning reduced coverage or degraded quality.`,
      state: 'DEGRADED',
      action: { href: '/eval', label: `Review ${label} runtime` },
    })
  }
  if (provider.status === 'UNAVAILABLE') {
    return availabilityFromDomain({
      key: `provider:${name}`,
      label,
      reason: provider.operatorAction ?? `No persisted ${label} observation is available yet.`,
      state: 'EMPTY',
      action: { href: '/eval', label: `Review ${label} runtime` },
    })
  }
  return null
}

export function providerDisplay(name: string, provider: ProviderState): string {
  const unavailable = availabilityFromProvider(name, provider)
  if (unavailable) return `${providerLabel(name)} · ${unavailable.state}`
  const source = provider.coverage ?? provider.mode.replaceAll('_', ' ').toUpperCase()
  return `${providerLabel(name)} · ${source} · ${provider.status ?? 'AVAILABLE'}`
}

export function dedupeAvailability(facts: AvailabilityFact[]): AvailabilityFact[] {
  const byKey = new Map<string, AvailabilityFact>()
  for (const fact of facts) {
    const existing = byKey.get(fact.key)
    if (!existing || priority[fact.state] > priority[existing.state]) byKey.set(fact.key, fact)
  }
  return [...byKey.values()]
}
