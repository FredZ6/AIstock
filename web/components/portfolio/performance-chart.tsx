'use client'

import { useId, useRef, useState } from 'react'
import Link from 'next/link'

import type { PortfolioSnapshot } from '../../lib/product-types'
import { normalizeDecimalSeries } from '../../lib/decimal'
import { formatMoney, formatPercent } from '../../lib/format'
import { parseAwareInstant } from '../../lib/time'

type Metric = 'cumulativeReturn' | 'dailyReturn' | 'drawdown' | 'nav'
type Range = 7 | 30 | 90 | 'all'

type MetricOption = { key: Metric; label: string }

const compactMetrics: MetricOption[] = [
  { key: 'nav', label: 'Net asset value' },
  { key: 'dailyReturn', label: 'Day return' },
  { key: 'drawdown', label: 'Current drawdown' },
]

const fullMetrics: MetricOption[] = [
  { key: 'nav', label: 'Net asset value' },
  { key: 'cumulativeReturn', label: 'Cumulative return' },
  { key: 'drawdown', label: 'Drawdown' },
]

function shortDate(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    day: 'numeric',
    month: 'short',
    timeZone: 'America/New_York',
  }).format(parseAwareInstant(value))
}

type PerformanceSnapshot = Pick<
  PortfolioSnapshot,
  'asOf' | 'currency' | 'dayReturn' | 'drawdown' | 'nav'
> & {
  performanceHistory: Array<Pick<
    PortfolioSnapshot['performanceHistory'][number],
    'drawdown' | 'nav' | 'time'
  > & { cumulativeReturn?: string | null; dailyReturn?: string | null }>
}

export function PerformanceChart({
  compact = false,
  snapshot,
}: {
  compact?: boolean
  snapshot: PerformanceSnapshot
}) {
  const metrics = compact ? compactMetrics : fullMetrics
  const [metric, setMetric] = useState<Metric>('nav')
  const chartId = useId()
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [range, setRange] = useState<Range>(30)
  const lastTime = parseAwareInstant(snapshot.performanceHistory.at(-1)?.time ?? snapshot.asOf).getTime()
  const visible = range === 'all'
    ? snapshot.performanceHistory
    : snapshot.performanceHistory.filter((point) => parseAwareInstant(point.time).getTime() >= lastTime - range * 86_400_000)
  const usable = visible.flatMap((point) => {
    const value = point[metric]
    return typeof value === 'string' ? [{ point, value }] : []
  })
  const normalizedValues = usable.length >= 2
    ? normalizeDecimalSeries(usable.map(({ value }) => value))
    : []
  const coordinates = normalizedValues.map((value, index) => ({
    x: index * 1000 / (usable.length - 1),
    y: 230 - value * 190,
  }))
  const line = coordinates.map((point, index) => `${index ? 'L' : 'M'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ')
  const area = coordinates.length ? `${line} L 1000 240 L 0 240 Z` : ''
  const selectedMetric = metrics.find((item) => item.key === metric)
  const selectedLabel = selectedMetric?.label ?? 'Performance'
  const first = usable.at(0)?.point
  const last = usable.at(-1)?.point

  return (
    <figure
      aria-label={compact ? 'Paper portfolio performance' : 'Portfolio performance'}
      className={`performance-overview${compact ? ' is-compact' : ''}`}
    >
      <figcaption className="performance-head">
        <div><p className="section-kicker">Paper portfolio</p><h2>Overview</h2></div>
        {compact ? <Link href="/portfolio">Open portfolio</Link> : (
          <div aria-label="Performance range" className="range-selector">
            {([7, 30, 90, 'all'] as const).map((value) => (
              <button aria-pressed={range === value} key={value} onClick={() => setRange(value)} type="button">
                {value === 'all' ? 'All history' : `Last ${value} days`}
              </button>
            ))}
          </div>
        )}
      </figcaption>

      <dl className="performance-facts">
        <div><dt>Net asset value</dt><dd>{formatMoney(snapshot.nav, snapshot.currency)}</dd></div>
        <div><dt>Day return</dt><dd>{formatPercent(snapshot.dayReturn)}</dd></div>
        <div><dt>Current drawdown</dt><dd>{formatPercent(snapshot.drawdown)}</dd></div>
      </dl>

      <div aria-label="Performance metric" className="metric-tabs" role="tablist">
        {metrics.map((item, index) => (
          <button
            aria-controls={`${chartId}-panel`}
            aria-selected={metric === item.key}
            id={`${chartId}-${item.key}`}
            key={item.key}
            onClick={() => setMetric(item.key)}
            onKeyDown={(event) => {
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? metrics.length - 1
                : event.key === 'ArrowRight' ? (index + 1) % metrics.length
                  : event.key === 'ArrowLeft' ? (index + metrics.length - 1) % metrics.length : null
              if (next === null) return
              event.preventDefault()
              setMetric(metrics[next].key)
              tabRefs.current[next]?.focus()
            }}
            ref={(node) => { tabRefs.current[index] = node }}
            role="tab"
            tabIndex={metric === item.key ? 0 : -1}
            type="button"
          >{item.label}</button>
        ))}
      </div>

      <div aria-labelledby={`${chartId}-${metric}`} className="performance-plot" data-metric={metric} id={`${chartId}-panel`} role="tabpanel" tabIndex={0}>
        {usable.length >= 2 ? <>
          <svg aria-label={`${selectedLabel} history`} preserveAspectRatio="none" role="img" viewBox="0 0 1000 260">
            <defs><linearGradient id="portfolio-performance-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopOpacity="0.32" /><stop offset="100%" stopOpacity="0" /></linearGradient></defs>
            <line className="chart-baseline" x1="0" x2="1000" y1="240" y2="240" />
            <path className="chart-area" d={area} />
            <path className="chart-line" d={line} />
          </svg>
          <div className="chart-dates"><time dateTime={first?.time}>{first ? shortDate(first.time) : '—'}</time><time dateTime={last?.time}>{last ? shortDate(last.time) : '—'}</time></div>
        </> : <p className="performance-history-empty">Not enough persisted history for this metric.</p>}
      </div>
      <p className="performance-fixture">{compact ? 'Frozen synthetic history' : 'Frozen synthetic performance history · not a real return record'}</p>
    </figure>
  )
}
