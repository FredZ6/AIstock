'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'

import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'

export type ResearchDirectorySymbol = {
  lastResearchAt: string | null
  opinion: string | null
  symbol: string
}

export function ResearchDirectoryPage(_props: {
  mode: 'api' | 'fixture'
  symbols: ResearchDirectorySymbol[]
  unavailableSymbols?: string[]
}) {
  const symbols = useMemo(
    () => [..._props.symbols].sort((left, right) => left.symbol.localeCompare(right.symbol)),
    [_props.symbols],
  )
  const recent = useMemo(
    () => symbols
      .filter((item): item is ResearchDirectorySymbol & { lastResearchAt: string } => item.lastResearchAt !== null)
      .sort((left, right) => right.lastResearchAt.localeCompare(left.lastResearchAt)),
    [symbols],
  )
  const [selected, setSelected] = useState(symbols[0]?.symbol ?? '')

  return <AppShell currentPath="/research">
    <section className="page-hero compact-hero">
      <div><p className="eyebrow">Research · {_props.mode === 'api' ? 'API Mode' : 'Fixture Mode'}</p><h1>Stock research</h1><p>Select from the authoritative watchlist universe, then open its evidence-backed research.</p></div>
    </section>
    {_props.unavailableSymbols?.length ? <section aria-label="Some recent research unavailable" className="state-surface surface-card" role="status">
      <p className="eyebrow">Degraded</p><h2>Some recent research unavailable</h2><p>Research history could not be read for {_props.unavailableSymbols.join(', ')}. The authoritative symbols remain selectable; no Fixture history was substituted.</p>
    </section> : null}
    {symbols.length ? <section className="terminal-section surface-card research-directory">
      <div className="section-heading"><div><p className="eyebrow">Discover</p><h2>Choose a stock</h2></div><span>{symbols.length} symbols</span></div>
      <div className="research-directory-control">
        <label>Research symbol<select aria-label="Research symbol" value={selected} onChange={(event) => setSelected(event.target.value)}>{symbols.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol}</option>)}</select></label>
        <Link className="button-link" href={`/research/${selected}`}>Open {selected} research</Link>
      </div>
    </section> : <section aria-label="No research symbols available" className="state-surface surface-card" role="status">
      <p className="eyebrow">Empty</p><h2>No research symbols available</h2><p>The authoritative watchlist is empty. Add a stock to the Watchlist before starting research.</p>
      <Link href="/watchlist">Open Watchlist</Link>
    </section>}
    {recent.length ? <section className="terminal-section surface-card research-directory">
      <div className="section-heading"><div><p className="eyebrow">Continue</p><h2>Recent persisted research</h2></div><span>{recent.length} records</span></div>
      <ul className="research-directory-list">{recent.map((item) => <li key={item.symbol}><Link href={`/research/${item.symbol}`}><strong>{item.symbol}</strong><span>{item.opinion ?? 'Unavailable'}</span><time dateTime={item.lastResearchAt}>{formatDualTime(item.lastResearchAt).newYork}</time></Link></li>)}</ul>
    </section> : null}
  </AppShell>
}
