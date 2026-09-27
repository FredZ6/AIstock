'use client'

import { useId, useState } from 'react'

import type { TodayDashboardWatchlistPanel } from './today-dashboard-model'

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
        {panel.action}
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
    {panel.context}
    <ul
      aria-label="Watchlist signals"
      className={`market-list watchlist-heatmap${mode === 'api' ? ' persisted-market-list' : ''}`}
      id={listId}
    >
      {visibleItems}
    </ul>
  </section>
}
