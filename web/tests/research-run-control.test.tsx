import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { startResearchRunAction } from '../app/research/actions'
import { ResearchRunControl } from '../components/research/research-run-control'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('../app/research/actions', () => ({
  startResearchRunAction: vi.fn(),
}))

const startRun = vi.mocked(startResearchRunAction)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ResearchRunControl', () => {
  it('keeps its idempotency key and navigates only after successful admission', async () => {
    startRun.mockResolvedValue({
      message: 'Deterministic research run queued.',
      runId: '10000000-0000-0000-0000-000000000099',
      status: 'success',
      symbol: 'NVDA',
    })
    const { rerender } = render(
      <ResearchRunControl idempotencyKey="research-form-1" symbol="NVDA" />,
    )

    expect(screen.getByDisplayValue('research-form-1')).toHaveAttribute('type', 'hidden')
    rerender(<ResearchRunControl idempotencyKey="research-form-1" symbol="NVDA" />)
    expect(screen.getByDisplayValue('research-form-1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Run deterministic research' }))

    await waitFor(() => expect(push).toHaveBeenCalledWith(
      '/runs/10000000-0000-0000-0000-000000000099',
    ))
  })
})
