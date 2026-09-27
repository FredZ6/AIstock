import { describe, expect, it } from 'vitest'

import { awareInstantKey, formatDualTime } from '../lib/time'

describe('aware time presentation', () => {
  it('rejects a naive datetime before formatting it', () => {
    expect(() => formatDualTime('2026-08-21T20:00:00')).toThrow(/timezone/i)
  })

  it('accepts an explicit UTC offset', () => {
    expect(formatDualTime('2026-08-21T16:00:00-04:00').newYork).toMatch(/Aug 21, 2026/)
  })

  it('preserves sub-millisecond ordering exactly', () => {
    expect(awareInstantKey('2026-08-21T20:00:00.123100Z'))
      .toBeLessThan(awareInstantKey('2026-08-21T20:00:00.123900Z'))
  })

  it('normalizes equivalent timezone offsets to one exact key', () => {
    expect(awareInstantKey('2026-08-21T16:00:00.123456789-04:00'))
      .toBe(awareInstantKey('2026-08-21T20:00:00.123456789Z'))
  })

  it('rejects invalid calendar dates instead of normalizing them', () => {
    expect(() => awareInstantKey('2026-02-30T20:00:00Z')).toThrow(/valid/i)
    expect(() => awareInstantKey('2026-08-21T20:00:00')).toThrow(/timezone/i)
  })
})
