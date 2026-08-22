const decimalPattern = /^(-?)(\d+)(?:\.(\d+))?$/

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
