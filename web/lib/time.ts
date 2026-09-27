const timeFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  })

const timezonePattern = /(Z|[+-]\d{2}:\d{2})$/
const rfc3339Pattern = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|([+-])(\d{2}):(\d{2}))$/

const nanosecondsPerSecond = 1_000_000_000n
const secondsPerDay = 86_400n

function isLeapYear(year: bigint) {
  return year % 4n === 0n && (year % 100n !== 0n || year % 400n === 0n)
}

function daysInMonth(year: bigint, month: bigint) {
  if (month === 2n) return isLeapYear(year) ? 29n : 28n
  if (month === 4n || month === 6n || month === 9n || month === 11n) return 30n
  return 31n
}

function daysSinceUnixEpoch(year: bigint, month: bigint, day: bigint) {
  const adjustedYear = year - (month <= 2n ? 1n : 0n)
  const era = adjustedYear / 400n
  const yearOfEra = adjustedYear - era * 400n
  const adjustedMonth = month + (month > 2n ? -3n : 9n)
  const dayOfYear = (153n * adjustedMonth + 2n) / 5n + day - 1n
  const dayOfEra = yearOfEra * 365n + yearOfEra / 4n - yearOfEra / 100n + dayOfYear
  return era * 146_097n + dayOfEra - 719_468n
}

export function awareInstantKey(value: string) {
  if (!timezonePattern.test(value)) {
    throw new TypeError('Datetime must include a timezone')
  }
  const match = rfc3339Pattern.exec(value)
  if (!match) throw new TypeError('Datetime must be valid RFC3339')

  const [, yearText, monthText, dayText, hourText, minuteText, secondText, fraction = '', zone, sign, offsetHourText = '00', offsetMinuteText = '00'] = match
  const year = BigInt(yearText)
  const month = BigInt(monthText)
  const day = BigInt(dayText)
  const hour = BigInt(hourText)
  const minute = BigInt(minuteText)
  const second = BigInt(secondText)
  const offsetHour = BigInt(offsetHourText)
  const offsetMinute = BigInt(offsetMinuteText)

  if (
    year < 1n || month < 1n || month > 12n || day < 1n || day > daysInMonth(year, month)
    || hour > 23n || minute > 59n || second > 59n || offsetHour > 23n || offsetMinute > 59n
  ) {
    throw new TypeError('Datetime must be valid RFC3339')
  }

  const localSeconds = daysSinceUnixEpoch(year, month, day) * secondsPerDay
    + hour * 3_600n + minute * 60n + second
  const offsetMagnitude = offsetHour * 3_600n + offsetMinute * 60n
  const offsetSeconds = zone === 'Z' ? 0n : sign === '+' ? offsetMagnitude : -offsetMagnitude
  const fractionalNanoseconds = BigInt(fraction.padEnd(9, '0') || '0')
  return (localSeconds - offsetSeconds) * nanosecondsPerSecond + fractionalNanoseconds
}

export function parseAwareInstant(value: string) {
  awareInstantKey(value)
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
