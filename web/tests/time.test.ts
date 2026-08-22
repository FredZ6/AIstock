import { describe, expect, it } from 'vitest'

import { formatDualTime } from '../lib/time'

describe('aware time presentation', () => {
  it('rejects a naive datetime before formatting it', () => {
    expect(() => formatDualTime('2026-08-21T20:00:00')).toThrow(/timezone/i)
  })

  it('accepts an explicit UTC offset', () => {
    expect(formatDualTime('2026-08-21T16:00:00-04:00').newYork).toMatch(/Aug 21, 2026/)
  })
})
