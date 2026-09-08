export type AgentEvent = {
  event_id: string
  event_time: string
  payload: Record<string, unknown>
  run_id: string
  schema_version: string
  sequence: number
  type: string
}

const timezonePattern = /(Z|[+-]\d{2}:\d{2})$/

function parseAgentEvent(value: unknown): AgentEvent {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('SSE data must be an agent event object')
  }
  const candidate = value as Partial<AgentEvent>
  if (
    typeof candidate.event_id !== 'string' ||
    typeof candidate.event_time !== 'string' ||
    !candidate.payload ||
    typeof candidate.payload !== 'object' ||
    Array.isArray(candidate.payload) ||
    typeof candidate.run_id !== 'string' ||
    typeof candidate.schema_version !== 'string' ||
    typeof candidate.sequence !== 'number' ||
    typeof candidate.type !== 'string'
  ) {
    throw new TypeError('SSE data does not match the agent event contract')
  }
  return candidate as AgentEvent
}

export class IncrementalSseParser {
  #buffer = ''
  #finished = false

  push(chunk: string): AgentEvent[] {
    if (this.#finished) throw new TypeError('Cannot append to a finished SSE parser')
    this.#buffer = `${this.#buffer}${chunk}`.replaceAll('\r\n', '\n')
    const events: AgentEvent[] = []
    let boundary = this.#buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = this.#buffer.slice(0, boundary)
      this.#buffer = this.#buffer.slice(boundary + 2)
      const parsed = this.#parseFrame(frame)
      if (parsed) events.push(parsed)
      boundary = this.#buffer.indexOf('\n\n')
    }
    return events
  }

  finish(): AgentEvent[] {
    if (this.#finished) return []
    this.#finished = true
    const frame = this.#buffer.replaceAll('\r\n', '\n')
    this.#buffer = ''
    const parsed = this.#parseFrame(frame)
    return parsed ? [parsed] : []
  }

  #parseFrame(frame: string): AgentEvent | undefined {
    let eventType: string | undefined
    const data: string[] = []
    for (const line of frame.split('\n')) {
      if (!line || line.startsWith(':')) continue
      const separator = line.indexOf(':')
      const field = separator < 0 ? line : line.slice(0, separator)
      let value = separator < 0 ? '' : line.slice(separator + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') eventType = value
      if (field === 'data') data.push(value)
    }
    if (data.length === 0) return undefined
    const event = parseAgentEvent(JSON.parse(data.join('\n')))
    if (eventType && event.type !== eventType) {
      throw new TypeError('SSE event type does not match its data payload')
    }
    return event
  }
}

export function reconnectRequest(baseUrl: string, runId: string, lastEventId?: string) {
  const separator = baseUrl.includes('?') ? '&' : '?'
  return {
    url: `${baseUrl}${separator}run_id=${encodeURIComponent(runId)}`,
    headers: lastEventId ? { 'Last-Event-ID': lastEventId } : {},
  }
}

export class DurableEventStore {
  readonly #byId = new Map<string, AgentEvent>()
  readonly #bySequence = new Map<number, string>()

  constructor(readonly runId: string) {}

  append(event: AgentEvent): boolean {
    if (event.run_id !== this.runId) {
      throw new TypeError('SSE run mismatch')
    }
    if (!timezonePattern.test(event.event_time) || Number.isNaN(Date.parse(event.event_time))) {
      throw new TypeError('SSE event_time must include a timezone')
    }
    if (!Number.isInteger(event.sequence) || event.sequence < 1) {
      throw new TypeError('SSE sequence must be a positive integer')
    }
    if (this.#byId.has(event.event_id)) {
      return false
    }
    const priorId = this.#bySequence.get(event.sequence)
    if (priorId) {
      throw new TypeError(`SSE sequence collision: ${event.sequence} is already ${priorId}`)
    }
    this.#byId.set(event.event_id, event)
    this.#bySequence.set(event.sequence, event.event_id)
    return true
  }

  get events(): AgentEvent[] {
    return Array.from(this.#byId.values()).sort((left, right) => left.sequence - right.sequence)
  }

  get lastEventId(): string | undefined {
    return this.events.at(-1)?.event_id
  }
}
