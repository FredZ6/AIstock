import type { ReactNode } from 'react'

import type { DataQuality } from '../../lib/api'
import { formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'

export function Signal({ children, tone }: { children: ReactNode; tone: string }) {
  return <span className="signal" data-tone={tone.toLowerCase()}><span aria-hidden="true" className="signal-dot" />{children}</span>
}

export function FixtureNotice() {
  return <div className="fixture-notice" role="note"><strong>Fixture Mode</strong><span>Frozen synthetic fixture · not current market data</span></div>
}

export function PageHeading({ eyebrow, summary, title, asOf }: { asOf: string; eyebrow: string; summary: string; title: string }) {
  const times = formatDualTime(asOf)
  return (
    <header className="today-heading page-heading">
      <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="today-summary">{summary}</p></div>
      <div className="time-context" aria-label="Snapshot time">
        <p><span>New York</span><time dateTime={asOf}>{times.newYork}</time></p>
        <p><span>Shanghai</span><time dateTime={asOf}>{times.shanghai}</time></p>
      </div>
    </header>
  )
}

export function QualityFacts({ quality }: { quality: DataQuality }) {
  return (
    <span className="quality-line">
      <span>{quality.freshness}</span>
      <span>{formatPercent(quality.coverage, { fractionDigits: 0, signed: false })} coverage</span>
      <span>{quality.provider}</span>
      <span>{quality.delaySeconds}s delay</span>
      <span>{quality.conflict ? 'Conflict detected' : 'No conflict'}</span>
    </span>
  )
}
