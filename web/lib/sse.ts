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
