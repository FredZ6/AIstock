'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import { DurableEventStore, IncrementalSseParser, type AgentEvent } from '../../lib/sse'
import type { ResearchRun } from '../../lib/server/live-data-api'
import { formatDualTime } from '../../lib/time'
import { Signal } from '../ui/product-ui'

type ConnectionState = 'Connecting' | 'Live' | 'Reconnecting' | 'Terminal'
const terminalStatuses = new Set<ResearchRun['status']>(['COMPLETED', 'FAILED', 'CANCELLED'])
const terminalEvents = new Set(['run.completed', 'run.failed', 'run.cancelled'])
const reconnectDelays = [250, 1_000, 2_000, 5_000]

export function LiveRunTrace({ initialRun }: { initialRun: ResearchRun }) {
  const { refresh } = useRouter()
  const store = useMemo(() => new DurableEventStore(initialRun.runId), [initialRun.runId])
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [connection, setConnection] = useState<ConnectionState>('Connecting')

  useEffect(() => {
    const replayOnly = terminalStatuses.has(initialRun.status)
    const controller = new AbortController()
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    let attempt = 0

    const accept = (received: AgentEvent[]) => {
      let changed = false
      let terminal = false
      for (const item of received) {
        changed = store.append(item) || changed
        terminal = terminalEvents.has(item.type) || terminal
      }
      if (changed) setEvents(store.events)
      if (terminal) {
        stopped = true
        setConnection('Terminal')
        if (!replayOnly) refresh()
      }
    }

    const connect = async () => {
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' }
        if (store.lastEventId) headers['Last-Event-ID'] = store.lastEventId
        const response = await fetch(`/api/research-runs/${initialRun.runId}/events`, {
          cache: 'no-store', headers, signal: controller.signal,
        })
        if (!response.ok || !response.body) throw new TypeError('Agent event stream unavailable')
        setConnection('Live')
        attempt = 0
        const parser = new IncrementalSseParser()
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        while (!stopped) {
          const result = await reader.read()
          if (result.done) break
          accept(parser.push(decoder.decode(result.value, { stream: true })))
        }
        if (!stopped) accept(parser.push(decoder.decode()))
        if (!stopped) accept(parser.finish())
        if (replayOnly) {
          stopped = true
          setConnection('Terminal')
        }
      } catch (error) {
        if (controller.signal.aborted) return
        console.error('agent-event-stream-failure', { runId: initialRun.runId, error })
      }
      if (!stopped && !controller.signal.aborted) {
        setConnection('Reconnecting')
        const delay = reconnectDelays[Math.min(attempt, reconnectDelays.length - 1)]
        attempt += 1
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    void connect()
    return () => {
      stopped = true
      controller.abort()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [initialRun.runId, initialRun.status, refresh, store])

  const currentNode = [...events].reverse().find((item) => typeof item.payload.node === 'string')?.payload.node
  const elapsedMs = events.length
    ? Math.max(0, Date.parse(events.at(-1)!.event_time) - Date.parse(initialRun.decisionTime))
    : 0
  const retries = events.filter((item) => item.type.includes('retry')).length
  const degradations = events.filter((item) => /degrad|fallback|unavailable/.test(item.type)).length
  const checkpoints = events.filter((item) => item.type.startsWith('checkpoint.')).length

  return <>
    <section className="run-overview" aria-label="Run operations summary">
      <div><p className="section-kicker">Status</p><Signal tone={initialRun.status}>{initialRun.status}</Signal><small>{initialRun.runId}</small></div>
      <div>
        <div role="status" aria-label="Agent event connection" className="muted-copy">Event stream · {connection}</div>
        <dl className="run-progress-facts">
          <div><dt>Elapsed</dt><dd>{elapsedMs.toLocaleString('en-US')} ms</dd></div>
          <div><dt>Current node</dt><dd>{typeof currentNode === 'string' ? currentNode : initialRun.status === 'QUEUED' ? 'Awaiting worker' : 'No node persisted'}</dd></div>
          <div><dt>Retries</dt><dd>{retries}</dd></div><div><dt>Degradations</dt><dd>{degradations}</dd></div>
          <div><dt>Checkpoints</dt><dd>{checkpoints}</dd></div>
          <div><dt>Data cutoff</dt><dd><time dateTime={initialRun.dataCutoff}>{formatDualTime(initialRun.dataCutoff).newYork}</time></dd></div>
          <div><dt>Resume cursor</dt><dd>{store.lastEventId ?? 'No event received'}</dd></div>
        </dl>
      </div>
    </section>
    <section className="terminal-section first-section" aria-labelledby="live-events-title">
      <div className="section-heading"><div><p className="section-kicker">Sequence</p><h2 id="live-events-title">Durable event trace</h2></div><span className="muted-copy">Authoritative persisted events</span></div>
      {events.length ? <ol aria-label="Durable run events" className="trace-list">{events.map((item) => <li key={item.event_id}>
        <span className="trace-sequence">{String(item.sequence).padStart(2, '0')}</span>
        <div><div className="trace-title"><strong>{item.type}</strong></div><p>{typeof item.payload.node === 'string' ? item.payload.node : JSON.stringify(item.payload)}</p><small>{item.event_id} · <time dateTime={item.event_time}>{formatDualTime(item.event_time).newYork}</time></small></div>
      </li>)}</ol> : <p className="unavailable-value">No durable event received yet.</p>}
    </section>
  </>
}
