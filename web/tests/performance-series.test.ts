import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { toAuthoritativePerformanceSeries, toPerformanceSeries } from '../components/portfolio/performance-series'

describe('toPerformanceSeries', () => {
  it('derives daily return and running-peak drawdown from ordered Decimal NAV values', () => {
    expect(toPerformanceSeries([
      { nav: '100.00', availableAt: '2026-09-25T20:00:00Z' },
      { nav: '110.00', availableAt: '2026-09-26T20:00:00Z' },
      { nav: '99.00', availableAt: '2026-09-27T20:00:00Z' },
    ])).toEqual([
      { nav: '100.00', dailyReturn: null, drawdown: '0.00000000', time: '2026-09-25T20:00:00Z' },
      { nav: '110.00', dailyReturn: '0.10000000', drawdown: '0.00000000', time: '2026-09-26T20:00:00Z' },
      { nav: '99.00', dailyReturn: '-0.10000000', drawdown: '-0.10000000', time: '2026-09-27T20:00:00Z' },
    ])
  })

  it('preserves input order', () => {
    expect(toPerformanceSeries([
      { nav: '90.00', availableAt: '2026-09-27T20:00:00Z' },
      { nav: '100.00', availableAt: '2026-09-25T20:00:00Z' },
    ]).map((point) => point.time)).toEqual([
      '2026-09-27T20:00:00Z',
      '2026-09-25T20:00:00Z',
    ])
  })

  it('leaves the daily return empty for a single point', () => {
    expect(toPerformanceSeries([
      { nav: '100.00', availableAt: '2026-09-25T20:00:00Z' },
    ])).toEqual([
      { nav: '100.00', dailyReturn: null, drawdown: '0.00000000', time: '2026-09-25T20:00:00Z' },
    ])
  })

  it('does not use Number for financial derivation', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'components/portfolio/performance-series.ts'),
      'utf8',
    )

    expect(source).not.toMatch(/\bNumber\s*\(/)
    expect(source).not.toMatch(/parseFloat|parseInt/)
  })
})

describe('toAuthoritativePerformanceSeries', () => {
  const latestNav = {
    availableAt: '2026-09-27T20:01:00Z',
    eventTime: '2026-09-27T20:00:00Z',
    id: 'nav-latest',
    nav: '110.00',
  }

  it('uses the availability-latest record at each earlier event time', () => {
    expect(toAuthoritativePerformanceSeries([
      { availableAt: '2026-09-26T20:01:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-earlier', nav: '200.00' },
      { availableAt: '2026-09-25T20:01:00Z', eventTime: '2026-09-25T20:00:00Z', id: 'nav-peak', nav: '130.00' },
      { availableAt: '2026-09-26T20:02:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-corrected', nav: '120.00' },
      latestNav,
    ], latestNav)).toEqual({
      latest: { nav: '110.00', dailyReturn: '-0.08333333', drawdown: '-0.15384615', time: '2026-09-27T20:01:00Z' },
      points: [
        { nav: '130.00', dailyReturn: null, drawdown: '0.00000000', time: '2026-09-25T20:01:00Z' },
        { nav: '120.00', dailyReturn: '-0.07692308', drawdown: '-0.07692308', time: '2026-09-26T20:02:00Z' },
        { nav: '110.00', dailyReturn: '-0.08333333', drawdown: '-0.15384615', time: '2026-09-27T20:01:00Z' },
      ],
    })
  })

  it('uses the lexicographically greatest id when availability ties', () => {
    const result = toAuthoritativePerformanceSeries([
      { availableAt: '2026-09-26T20:02:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-001', nav: '100.00' },
      { availableAt: '2026-09-26T20:02:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-002', nav: '120.00' },
      latestNav,
    ], latestNav)

    expect(result.points[0]?.nav).toBe('120.00')
    expect(result.latest?.dailyReturn).toBe('-0.08333333')
  })

  it('keeps sub-millisecond events distinct and selects the truly latest correction', () => {
    const preciseLatest = {
      availableAt: '2026-09-26T20:00:00.124100Z',
      eventTime: '2026-09-26T20:00:00.124000Z',
      id: 'nav-latest-precise',
      nav: '130.00',
    }
    const result = toAuthoritativePerformanceSeries([
      { availableAt: '2026-09-26T20:00:00.123950Z', eventTime: '2026-09-26T20:00:00.123900Z', id: 'nav-second', nav: '125.00' },
      { availableAt: '2026-09-26T20:00:00.123100Z', eventTime: '2026-09-26T20:00:00.123100Z', id: 'nav-z-early-correction', nav: '100.00' },
      { availableAt: '2026-09-26T20:00:00.123900Z', eventTime: '2026-09-26T20:00:00.123100Z', id: 'nav-a-late-correction', nav: '120.00' },
      preciseLatest,
    ], preciseLatest)

    expect(result.points.map((point) => point.nav)).toEqual(['120.00', '125.00', '130.00'])
    expect(result.latest?.dailyReturn).toBe('0.04000000')
  })

  it('canonicalizes equivalent event instants with different offsets into one bucket', () => {
    const result = toAuthoritativePerformanceSeries([
      { availableAt: '2026-09-26T16:01:00-04:00', eventTime: '2026-09-26T16:00:00-04:00', id: 'nav-offset', nav: '100.00' },
      { availableAt: '2026-09-26T20:02:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-utc', nav: '120.00' },
      latestNav,
    ], latestNav)

    expect(result.points.map((point) => point.nav)).toEqual(['120.00', '110.00'])
  })

  it('fails closed to one authoritative point when latestNav id is absent', () => {
    expect(toAuthoritativePerformanceSeries([
      { availableAt: '2026-09-26T20:02:00Z', eventTime: '2026-09-26T20:00:00Z', id: 'nav-other', nav: '120.00' },
    ], latestNav)).toEqual({
      latest: null,
      points: [
        { nav: '110.00', dailyReturn: null, drawdown: '0.00000000', time: '2026-09-27T20:01:00Z' },
      ],
    })
  })
})
