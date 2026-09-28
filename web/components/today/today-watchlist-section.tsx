'use client'

import { useId, useState } from 'react'
import Link from 'next/link'

import type { TodayDashboardWatchlistPanel } from './today-dashboard-model'
import { formatDualTime } from '../../lib/time'
import { Signal } from '../ui/product-ui'

const collapsedItemCount = 2

export function TodayWatchlistSection({ mode, panel }: { mode: 'api' | 'fixture'; panel: TodayDashboardWatchlistPanel }) {
  const [expanded, setExpanded] = useState(false)
  const generatedId = useId()
  const listId = `today-watchlist-${generatedId.replaceAll(':', '')}`
  const hasDisclosure = panel.items.length > collapsedItemCount
  const visibleItems = expanded ? panel.items : panel.items.slice(0, collapsedItemCount)

  return <section aria-label="Watchlist signals" className="terminal-section today-watchlist">
    <div className="section-heading">
      <div><p className="section-kicker">{panel.kicker}</p><h2>{panel.title}</h2></div>
      <div className="watchlist-heading-actions">
        {panel.action ? <Link className="compact-hit-link" href={panel.action.href}>{panel.action.label}</Link> : null}
        {hasDisclosure ? <button
          aria-controls={listId}
          aria-expanded={expanded}
          className="compact-hit-link"
          onClick={() => setExpanded((current) => !current)}
          type="button"
        >
          {expanded ? 'Show less' : `Show all (${panel.items.length})`}
        </button> : null}
      </div>
    </div>
    {panel.context ? <p className="muted-copy"><span>{panel.context.label}</span>{expanded || !hasDisclosure ? <small>{panel.context.detail}</small> : null}</p> : null}
    <ul
      aria-label="Watchlist signals"
      className={`market-list watchlist-heatmap${mode === 'api' ? ' persisted-market-list' : ''}`}
      id={listId}
    >
      {visibleItems.map((item) => <li key={item.symbol} data-direction={item.direction}>
        <div className="heatmap-primary"><Link className="compact-hit-link" href={`/research/${item.symbol}`}>{item.symbol}</Link><strong>{item.primaryValue}</strong></div>
        {item.decisions.length ? <div className="heatmap-decisions">{item.decisions.map((decision) => <Signal key={`${decision.tone}:${decision.label}`} tone={decision.tone}>{decision.label}</Signal>)}</div> : null}
        {item.detail ? <span className="unavailable-value">{item.detail}</span> : null}
        {item.summary && (expanded || !hasDisclosure) ? <p>{item.summary}</p> : null}
        {expanded || !hasDisclosure ? <div className="quality-line">{item.provenance.map((value) => <span key={value}>{value}</span>)}{item.availableAt ? <time dateTime={item.availableAt}>Available {formatDualTime(item.availableAt).newYork}</time> : null}</div> : null}
      </li>)}
    </ul>
  </section>
}
