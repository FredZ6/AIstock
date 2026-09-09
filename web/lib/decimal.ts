const decimalPattern = /^(-?)(\d+)(?:\.(\d+))?$/

function decimalInteger(value: string, scale: number): bigint {
  const match = decimalPattern.exec(value)
  if (!match) throw new TypeError('Value must be a Decimal string')
  const magnitude = BigInt(`${match[2]}${(match[3] ?? '').padEnd(scale, '0')}`)
  return match[1] === '-' ? -magnitude : magnitude
}

export function decimalChange(current: string, baseline: string, fractionDigits = 8): string {
  const currentMatch = decimalPattern.exec(current)
  const baselineMatch = decimalPattern.exec(baseline)
  if (!currentMatch || !baselineMatch) throw new TypeError('Value must be a Decimal string')
  const scale = Math.max((currentMatch[3] ?? '').length, (baselineMatch[3] ?? '').length)
  const currentInteger = decimalInteger(current, scale)
  const baselineInteger = decimalInteger(baseline, scale)
  if (baselineInteger <= 0n) throw new RangeError('Baseline must be positive')
  const targetScale = 10n ** BigInt(fractionDigits)
  const numerator = (currentInteger - baselineInteger) * targetScale
  const negative = numerator < 0n
  const magnitude = negative ? -numerator : numerator
  let quotient = magnitude / baselineInteger
  if ((magnitude % baselineInteger) * 2n >= baselineInteger) quotient += 1n
  const raw = quotient.toString().padStart(fractionDigits + 1, '0')
  const formatted = `${raw.slice(0, -fractionDigits)}.${raw.slice(-fractionDigits)}`
  return `${negative && quotient !== 0n ? '-' : ''}${formatted}`
}

export function compareDecimals(left: string, right: string): number {
  const leftMatch = decimalPattern.exec(left)
  const rightMatch = decimalPattern.exec(right)
  if (!leftMatch || !rightMatch) throw new TypeError('Value must be a Decimal string')
  const scale = Math.max((leftMatch[3] ?? '').length, (rightMatch[3] ?? '').length)
  const leftInteger = decimalInteger(left, scale)
  const rightInteger = decimalInteger(right, scale)
  return leftInteger < rightInteger ? -1 : leftInteger > rightInteger ? 1 : 0
}

export function normalizeDecimalSeries(values: string[]): number[] {
  if (values.length === 0) return []

  const parsed = values.map((value) => {
    const match = decimalPattern.exec(value)
    if (!match) throw new TypeError('Chart value must be a Decimal string')
    return { negative: match[1] === '-', whole: match[2], fraction: match[3] ?? '' }
  })
  const scale = Math.max(...parsed.map(({ fraction }) => fraction.length))
  const integers = parsed.map(({ negative, whole, fraction }) => {
    const magnitude = BigInt(`${whole}${fraction.padEnd(scale, '0')}`)
    return negative ? -magnitude : magnitude
  })
  const low = integers.reduce((current, value) => value < current ? value : current)
  const high = integers.reduce((current, value) => value > current ? value : current)
  const spread = high - low
  if (spread === 0n) return integers.map(() => 0)

  const ratioScale = 1_000_000n
  return integers.map((value) => Number((value - low) * ratioScale / spread) / Number(ratioScale))
}
