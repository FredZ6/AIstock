import type { PerformanceSnapshot } from '../portfolio/performance-chart'

export type TodaySlot<T> =
  | { kind: 'available'; value: T }
  | { kind: 'degraded' | 'empty' | 'unavailable'; message: string }

export type TodayLink = { href: string; label: string }

export type TodayPortfolioView = {
  historySource?: { label: string; time: string }
  snapshot: PerformanceSnapshot
}

export type TodayMarketRegimeView = {
  benchmarks?: Array<{ label: string; value: string }>
  label: string
  metrics: Array<{ label: string; value: string }>
  model: string
  tone: string
}

export type TodayWatchlistItemView = {
  availableAt?: string
  decisions: Array<{ label: string; tone: string }>
  detail?: string
  direction?: 'negative' | 'positive'
  primaryValue: string
  provenance: string[]
  summary?: string
  symbol: string
}

export type TodayDashboardWatchlistPanel = {
  action?: TodayLink
  context?: { label: string; detail: string }
  items: TodayWatchlistItemView[]
  kicker: string
  title: string
}

export type TodayAlertView = {
  detail: string
  emphasis?: string
  eventTime: string
  id: string
  severity: string
  symbol: string
}

export type TodayAlertsPanel = {
  action?: TodayLink
  items: TodayAlertView[]
  kicker: string
  title: string
}

export type TodayRunView = {
  completedSteps?: number
  decisionTime?: string
  href: string
  label: string
  status: string
  totalSteps?: number
}

export type TodayDashboardModel = {
  activeRun: TodaySlot<TodayRunView>
  alerts: TodaySlot<TodayAlertsPanel>
  asOf: string
  heading: {
    eyebrow: string
    notice: { description: string; label: string }
    summary: string
    title: string
  }
  marketRegime: TodaySlot<TodayMarketRegimeView>
  mode: 'api' | 'fixture'
  portfolio: TodaySlot<TodayPortfolioView>
  watchlist: TodaySlot<TodayDashboardWatchlistPanel>
}
