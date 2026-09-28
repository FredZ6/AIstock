'use client'

import { useId, useRef, useState } from 'react'
import Link from 'next/link'

import type { PortfolioSnapshot } from '../../lib/product-types'
import { compareDecimals, normalizeDecimalSeries } from '../../lib/decimal'
import { formatMoney, formatPercent } from '../../lib/format'
import { formatDualTime, parseAwareInstant } from '../../lib/time'

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

export type PerformanceSnapshot = Pick<
  PortfolioSnapshot,
  'asOf' | 'currency' | 'nav'
> & {
  dayReturn: string | null
  drawdown: string | null
  performanceHistory: Array<Pick<
    PortfolioSnapshot['performanceHistory'][number],
    'drawdown' | 'nav' | 'time'
  > & { cumulativeReturn?: string | null; dailyReturn?: string | null }>
}

export function PerformanceChart({
  compact = false,
  historySource,
  snapshot,
}: {
  compact?: boolean
  historySource?: { label: string; time: string }
  snapshot: PerformanceSnapshot
}) {
  const metrics = compact ? compactMetrics : fullMetrics
  const [metric, setMetric] = useState<Metric>('nav')
  const chartId = useId()
  const gradientId = `${chartId.replaceAll(':', '')}-performance-fill`
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
  const first = usable.at(0)
  const last = usable.at(-1)
  const metricUnit = metric === 'nav' ? snapshot.currency : 'percent'
  const formatMetricValue = (value: string) => metric === 'nav'
    ? formatMoney(value, snapshot.currency)
    : formatPercent(value)
  const direction = first && last
    ? compareDecimals(last.value, first.value) < 0 ? 'decreased'
      : compareDecimals(last.value, first.value) > 0 ? 'increased' : 'was unchanged'
    : null
  const metricSummary = first && last && usable.length >= 2
    ? `${selectedLabel}, measured in ${metricUnit}, ${direction} from ${formatMetricValue(first.value)} on ${shortDate(first.point.time)} to ${formatMetricValue(last.value)} on ${shortDate(last.point.time)}.`
    : `${selectedLabel}, measured in ${metricUnit}: not enough persisted history for this metric.`
  const compactValues: Partial<Record<Metric, string>> = {
    dailyReturn: snapshot.dayReturn === null ? 'Unavailable' : formatPercent(snapshot.dayReturn),
    drawdown: snapshot.drawdown === null ? 'Unavailable' : formatPercent(snapshot.drawdown),
    nav: formatMoney(snapshot.nav, snapshot.currency),
  }

  const selectWithKeyboard = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? metrics.length - 1
      : event.key === 'ArrowRight' ? (index + 1) % metrics.length
        : event.key === 'ArrowLeft' ? (index + metrics.length - 1) % metrics.length : null
    if (next === null) return
    event.preventDefault()
    setMetric(metrics[next].key)
    tabRefs.current[next]?.focus()
  }

  const metricTab = (item: MetricOption, index: number, headline = false) => (
    <button
      aria-controls={`${chartId}-panel`}
      aria-describedby={headline ? `${chartId}-${item.key}-value` : undefined}
      aria-label={item.label}
      aria-selected={metric === item.key}
      id={`${chartId}-${item.key}`}
      key={item.key}
      onClick={() => setMetric(item.key)}
      onKeyDown={(event) => selectWithKeyboard(event, index)}
      ref={(node) => { tabRefs.current[index] = node }}
      role="tab"
      tabIndex={metric === item.key ? 0 : -1}
      type="button"
    >
      {headline ? <>
        <span className="performance-fact-label">{item.label}</span>
        <strong className="performance-fact-value" id={`${chartId}-${item.key}-value`}>{compactValues[item.key] ?? 'Unavailable'}</strong>
      </> : item.label}
    </button>
  )

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

      {compact ? (
        <div aria-label="Performance metric" className="performance-facts" role="tablist">
          {metrics.map((item, index) => metricTab(item, index, true))}
        </div>
      ) : <>
        <dl className="performance-facts">
          <div><dt>Net asset value</dt><dd>{formatMoney(snapshot.nav, snapshot.currency)}</dd></div>
          <div><dt>Day return</dt><dd>{snapshot.dayReturn === null ? 'Unavailable' : formatPercent(snapshot.dayReturn)}</dd></div>
          <div><dt>Current drawdown</dt><dd>{snapshot.drawdown === null ? 'Unavailable' : formatPercent(snapshot.drawdown)}</dd></div>
        </dl>
        <div aria-label="Performance metric" className="metric-tabs" role="tablist">
          {metrics.map((item, index) => metricTab(item, index))}
        </div>
      </>}

      <div aria-describedby={`${chartId}-summary`} aria-labelledby={`${chartId}-${metric}`} className="performance-plot" data-metric={metric} id={`${chartId}-panel`} role="tabpanel" tabIndex={0}>
        {usable.length >= 2 ? <>
          <svg aria-label={`${selectedLabel} history`} preserveAspectRatio="none" role="img" viewBox="0 0 1000 260">
            <defs><linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopOpacity="0.32" /><stop offset="100%" stopOpacity="0" /></linearGradient></defs>
            <line className="chart-baseline" x1="0" x2="1000" y1="240" y2="240" />
            <path className="chart-area" d={area} fill={`url(#${gradientId})`} />
            <path className="chart-line" d={line} />
          </svg>
          <div className="chart-dates"><time dateTime={first?.point.time}>{first ? shortDate(first.point.time) : '—'}</time><time dateTime={last?.point.time}>{last ? shortDate(last.point.time) : '—'}</time></div>
          <p className="performance-chart-summary" id={`${chartId}-summary`}>{metricSummary}</p>
        </> : <p className="performance-history-empty performance-chart-summary" id={`${chartId}-summary`}>{metricSummary}</p>}
      </div>
      <p className="performance-fixture">{historySource ? <>
        <span>{historySource.label}</span> · persisted <time dateTime={historySource.time}>{formatDualTime(historySource.time).newYork}</time>
      </> : compact ? 'Frozen synthetic history' : 'Frozen synthetic performance history · not a real return record'}</p>
    </figure>
  )
}
