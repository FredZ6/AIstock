import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LiveRunTrace } from '../components/trace/live-run-trace'
import type { AgentEvent } from '../lib/sse'
import type { ResearchRun } from '../lib/server/live-data-api'

const refresh = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }))

const run: ResearchRun = {
  dataCutoff: '2026-09-06T14:00:00Z',
  decisionTime: '2026-09-06T14:00:00Z',
  runId: '01991f2b-2bb4-7db1-8890-5ff287e11bb2',
  runType: 'RESEARCH',
  status: 'RUNNING',
  symbol: 'NVDA',
}

const event = (overrides: Partial<AgentEvent> = {}): AgentEvent => ({
  event_id: '01991f2b-2bb4-7db1-8890-5ff287e11bb3',
  event_time: '2026-09-06T14:00:02Z',
  payload: { node: 'collect_evidence', status: 'COMPLETED' },
  run_id: run.runId,
  schema_version: '1.0',
  sequence: 1,
  type: 'node.completed',
  ...overrides,
})

const frame = (value: AgentEvent) => `id: ${value.event_id}\nevent: ${value.type}\ndata: ${JSON.stringify(value)}\n\n`

afterEach(() => {
  vi.unstubAllGlobals()
  refresh.mockReset()
})

describe('live durable run trace', () => {
  it('renders ordered operational facts and deduplicates replayed events', async () => {
    const second = event({
      event_id: '01991f2b-2bb4-7db1-8890-5ff287e11bb4',
      event_time: '2026-09-06T14:00:04Z',
      payload: { node: 'verify_citations', status: 'COMPLETED' },
      sequence: 2,
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(frame(second) + frame(event()) + frame(second))))

    render(<LiveRunTrace initialRun={run} />)

    expect(screen.getByRole('region', { name: 'Run operations summary' })).toHaveTextContent('RUNNING')
    expect(screen.getByText('Data cutoff').parentElement).toHaveTextContent('Sep 6, 2026')
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    const rows = screen.getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('collect_evidence')
    expect(rows[1]).toHaveTextContent('verify_citations')
    expect(screen.getByText('Current node').parentElement).toHaveTextContent('verify_citations')
    expect(screen.getByText('Elapsed').parentElement).toHaveTextContent('4,000 ms')
    expect(screen.getByText('Retries').parentElement).toHaveTextContent('0')
    expect(screen.getByText('Degradations').parentElement).toHaveTextContent('0')
    expect(screen.getByText('Checkpoints').parentElement).toHaveTextContent('0')
    expect(screen.getByText('Resume cursor').parentElement).toHaveTextContent(second.event_id)
  })

  it('shows reconnecting after a disconnect without substituting Fixture content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('')))
    render(<LiveRunTrace initialRun={run} />)

    await waitFor(() => expect(screen.getByRole('status', { name: 'Agent event connection' })).toHaveTextContent('Reconnecting'))
    expect(screen.queryByText(/Fixture Mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('refreshes authoritative server data after a terminal event', async () => {
    const completed = event({ payload: { status: 'COMPLETED' }, type: 'run.completed' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(frame(completed))))
    render(<LiveRunTrace initialRun={run} />)

    await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  })

  it.each(['FAILED', 'CANCELLED'] as const)('keeps %s explicit while replaying persisted history once', async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(frame(event())))
    vi.stubGlobal('fetch', fetchMock)
    render(<LiveRunTrace initialRun={{ ...run, status }} />)

    expect(screen.getByText(status)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('collect_evidence')).toHaveLength(2))
    expect(screen.getByRole('status', { name: 'Agent event connection' })).toHaveTextContent('Terminal')
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(refresh).not.toHaveBeenCalled()
  })
})
