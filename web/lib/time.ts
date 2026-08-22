const timeFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  })

const timezonePattern = /(Z|[+-]\d{2}:\d{2})$/

export function parseAwareInstant(value: string) {
  if (!timezonePattern.test(value)) {
    throw new TypeError('Datetime must include a timezone')
  }
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) {
    throw new TypeError('Datetime must be valid')
  }
  return instant
}

export function formatDualTime(value: string) {
  const instant = parseAwareInstant(value)
  return {
    newYork: timeFormatter('America/New_York').format(instant),
    shanghai: timeFormatter('Asia/Shanghai').format(instant),
  }
}
