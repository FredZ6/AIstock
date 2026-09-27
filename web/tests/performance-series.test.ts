import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { toPerformanceSeries } from '../components/portfolio/performance-series'

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
