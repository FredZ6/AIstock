import { compareDecimals, decimalChange } from '../../lib/decimal'

type PersistedNavPoint = {
  nav: string
  availableAt: string
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
