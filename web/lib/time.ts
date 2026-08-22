const timeFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  })

export function formatDualTime(value: string) {
  const instant = new Date(value)
  return {
    newYork: timeFormatter('America/New_York').format(instant),
    shanghai: timeFormatter('Asia/Shanghai').format(instant),
  }
}
