import { compareDecimals, decimalChange } from '../../lib/decimal'
import { awareInstantKey } from '../../lib/time'

type PersistedNavPoint = {
  nav: string
  availableAt: string
}

type PersistedNavRecord = PersistedNavPoint & {
  eventTime: string
  id: string
  portfolioId: string
}

export type PerformancePoint = {
  nav: string
  dailyReturn: string | null
  drawdown: string
  time: string
}

export function toPerformanceSeries(points: PersistedNavPoint[]): PerformancePoint[] {
  let peak: string | null = null

  return points.map((point, index) => {
    const previous = points[index - 1]
    if (peak === null || compareDecimals(point.nav, peak) > 0) peak = point.nav

    return {
      nav: point.nav,
      dailyReturn: previous ? decimalChange(point.nav, previous.nav) : null,
      drawdown: decimalChange(point.nav, peak),
      time: point.availableAt,
    }
  })
}

export function toAuthoritativePerformanceSeries(
  history: PersistedNavRecord[],
  latestNav: PersistedNavRecord,
): { latest: PerformancePoint | null; points: PerformancePoint[] } {
  const failClosed = () => ({
    latest: null,
    points: toPerformanceSeries([{ availableAt: latestNav.availableAt, nav: latestNav.nav }]),
  })
  const latestEventTime = awareInstantKey(latestNav.eventTime)
  const latestAvailableTime = awareInstantKey(latestNav.availableAt)
  const matchesLatest = (point: PersistedNavRecord) => (
    point.id === latestNav.id
    && point.portfolioId === latestNav.portfolioId
    && compareDecimals(point.nav, latestNav.nav) === 0
    && awareInstantKey(point.eventTime) === latestEventTime
    && awareInstantKey(point.availableAt) === latestAvailableTime
  )
  const sameIdRecords = history.filter((point) => point.id === latestNav.id)
  const authoritativeRecordMatches = sameIdRecords.length > 0 && sameIdRecords.every(matchesLatest)
  const onePortfolio = history.every((point) => point.portfolioId === latestNav.portfolioId)
  const historyEndsAtLatest = history.every(
    (point) => awareInstantKey(point.eventTime) <= latestEventTime,
  )
  const latestEventRecords = history.filter(
    (point) => awareInstantKey(point.eventTime) === latestEventTime,
  )
  const canonicalLatest = latestEventRecords.reduce<PersistedNavRecord | null>((winner, point) => {
    if (!winner) return point
    const availableTime = awareInstantKey(point.availableAt)
    const winnerAvailableTime = awareInstantKey(winner.availableAt)
    return availableTime > winnerAvailableTime
      || (availableTime === winnerAvailableTime && point.id > winner.id)
      ? point
      : winner
  }, null)
  if (
    !authoritativeRecordMatches
    || !onePortfolio
    || !historyEndsAtLatest
    || canonicalLatest === null
    || !matchesLatest(canonicalLatest)
  ) {
    return failClosed()
  }

  const canonicalByEventTime = new Map<bigint, PersistedNavRecord>()

  for (const point of history) {
    const eventTime = awareInstantKey(point.eventTime)
    if (eventTime >= latestEventTime) continue

    const current = canonicalByEventTime.get(eventTime)
    if (!current) {
      canonicalByEventTime.set(eventTime, point)
      continue
    }

    const availableTime = awareInstantKey(point.availableAt)
    const currentAvailableTime = awareInstantKey(current.availableAt)
    // The greatest id wins an availability tie, matching the API history's id DESC tie-break.
    if (availableTime > currentAvailableTime || (availableTime === currentAvailableTime && point.id > current.id)) {
      canonicalByEventTime.set(eventTime, point)
    }
  }

  const canonicalHistory = [...canonicalByEventTime.entries()]
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([, point]) => ({ availableAt: point.availableAt, nav: point.nav }))
  const points = toPerformanceSeries([
    ...canonicalHistory,
    { availableAt: latestNav.availableAt, nav: latestNav.nav },
  ])

  return { latest: points.at(-1) ?? null, points }
}
