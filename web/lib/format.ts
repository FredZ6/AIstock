type PercentOptions = {
  fractionDigits?: number
  signed?: boolean
}

function scaledInteger(value: string, fractionDigits: number): { negative: boolean; value: bigint } {
  const negative = value.startsWith('-')
  const absolute = negative ? value.slice(1) : value
  const [whole, fraction = ''] = absolute.split('.')
  const coefficient = BigInt(`${whole}${fraction}`)
  const sourceScale = 10n ** BigInt(fraction.length)
  const targetScale = 10n ** BigInt(fractionDigits)
  const numerator = coefficient * targetScale
  let rounded = numerator / sourceScale
  if ((numerator % sourceScale) * 2n >= sourceScale) {
    rounded += 1n
  }
  return { negative, value: rounded }
}

function fixed(value: bigint, fractionDigits: number): string {
  const raw = value.toString().padStart(fractionDigits + 1, '0')
  if (fractionDigits === 0) {
    return raw
  }
  return `${raw.slice(0, -fractionDigits)}.${raw.slice(-fractionDigits)}`
}

export function formatMoney(value: string, currency: 'USD'): string {
  const scaled = scaledInteger(value, 2)
  const raw = fixed(scaled.value, 2)
  const [whole, fraction] = raw.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${currency} ${scaled.negative ? '-' : ''}${grouped}.${fraction}`
}

export function formatPercent(value: string, options: PercentOptions = {}): string {
  const fractionDigits = options.fractionDigits ?? 2
  const signed = options.signed ?? true
  const percentage = scaledInteger(value, fractionDigits + 2)
  const prefix = percentage.negative ? '-' : signed && percentage.value !== 0n ? '+' : ''
  return `${prefix}${fixed(percentage.value, fractionDigits)}%`
}
