import type { ReactNode } from 'react'

export type TodaySlot<T> =
  | { kind: 'available'; value: T }
  | { kind: 'degraded' | 'empty' | 'unavailable'; message: string }

export type TodayDashboardPanel = {
  action?: ReactNode
  content: ReactNode
  kicker: string
  title: string
}

export type TodayDashboardModel = {
  activeRun: TodaySlot<TodayDashboardPanel>
  alerts: TodaySlot<TodayDashboardPanel>
  asOf: string
  heading: {
    eyebrow: string
    notice: { description: string; label: string }
    summary: string
    title: string
  }
  marketRegime: TodaySlot<ReactNode>
  mode: 'api' | 'fixture'
  portfolio: TodaySlot<ReactNode>
  watchlist: TodaySlot<TodayDashboardPanel>
}
