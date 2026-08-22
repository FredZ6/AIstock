import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MissingFixturePage } from '../components/states/missing-fixture-page'
import { getFixtureResearchSnapshot, getFixtureRunTrace } from '../lib/fixtures'

describe('dynamic fixture routing', () => {
  it('never substitutes NVDA research for a symbol without a frozen fixture', () => {
    expect(getFixtureResearchSnapshot('nvda')?.symbol).toBe('NVDA')
    expect(getFixtureResearchSnapshot('MSFT')).toBeNull()
  })

  it('never substitutes the latest trace for an unknown run ID', () => {
    expect(getFixtureRunTrace('latest')?.runId).toBeTruthy()
    expect(getFixtureRunTrace('unknown-run')).toBeNull()
  })

  it('renders an honest empty state for unavailable fixture detail', () => {
    render(
      <MissingFixturePage
        currentPath="/research/NVDA"
        entity="MSFT research"
        returnHref="/watchlist"
        returnLabel="Return to watchlist"
      />,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'MSFT research' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Frozen fixture unavailable' })).toBeInTheDocument()
    expect(screen.queryByText(/NVDA research/i)).not.toBeInTheDocument()
  })
})
