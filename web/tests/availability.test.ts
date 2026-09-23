import { describe, expect, it } from 'vitest'

import {
  availabilityFromDomain,
  availabilityFromProvider,
  dedupeAvailability,
  providerDisplay,
} from '../lib/availability'

describe('canonical availability', () => {
  it.each([
    ['No persisted records exist yet.', 'EMPTY'],
    ['No approved provider or producer exists for this domain.', 'UNSUPPORTED'],
    ['Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar.', 'UNCONFIGURED'],
    ['The latest persisted observation is stale.', 'STALE'],
    ['Coverage is degraded by a provider gap.', 'DEGRADED'],
    ['The API request failed contract validation.', 'FAILURE'],
  ] as const)('classifies %s as %s', (reason, expected) => {
    expect(availabilityFromDomain({ key: expected, label: 'Fact', reason }).state).toBe(expected)
  })

  it('uses one provider rule for both summary inclusion and display', () => {
    const configuredSec = { configured: true, mode: 'read_only' as const }
    const missingAlpha = {
      configured: false,
      mode: 'unavailable' as const,
      operatorAction: 'Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar.',
    }

    expect(availabilityFromProvider('sec', configuredSec)).toBeNull()
    expect(providerDisplay('sec', configuredSec)).toBe('SEC · READ ONLY · AVAILABLE')
    expect(availabilityFromProvider('alpha_vantage', missingAlpha)).toMatchObject({
      label: 'ALPHA VANTAGE',
      state: 'UNCONFIGURED',
      reason: missingAlpha.operatorAction,
    })
    expect(providerDisplay('alpha_vantage', missingAlpha)).toBe('ALPHA VANTAGE · UNCONFIGURED')
  })

  it('keeps the strongest duplicate state and its recovery action', () => {
    const facts = dedupeAvailability([
      { key: 'sec', label: 'SEC filings', state: 'EMPTY', reason: 'No filing was persisted.', action: null },
      { key: 'sec', label: 'SEC filings', state: 'FAILURE', reason: 'SEC ingestion failed.', action: { href: '/eval', label: 'Review runtime' } },
    ])

    expect(facts).toEqual([{
      key: 'sec', label: 'SEC filings', state: 'FAILURE', reason: 'SEC ingestion failed.',
      action: { href: '/eval', label: 'Review runtime' },
    }])
  })
})
