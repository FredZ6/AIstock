import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addWatchlistAction,
  deleteWatchlistAction,
  updateWatchlistAction,
} from '../app/watchlist/actions'
import { WatchlistApiControls } from '../components/watchlist/watchlist-api-controls'

vi.mock('../app/watchlist/actions', () => ({
  addWatchlistAction: vi.fn(),
  deleteWatchlistAction: vi.fn(),
  updateWatchlistAction: vi.fn(),
}))

const addItem = vi.mocked(addWatchlistAction)
const deleteItem = vi.mocked(deleteWatchlistAction)
const updateItem = vi.mocked(updateWatchlistAction)

const item = {
  alertThreshold: '0.025',
  createdAt: '2026-08-23T00:00:00+00:00',
  dailyResearch: true,
  enrichment: {
    kind: 'unavailable' as const,
    missing: ['market', 'research', 'earnings', 'data-quality'],
  },
  intradayMonitoring: false,
  symbol: 'NVDA',
  updatedAt: '2026-08-23T00:05:00+00:00',
}

function renderControls() {
  return render(
    <WatchlistApiControls
      asOf="2026-09-12T04:00:00Z"
      items={[item]}
      quotes={[]}
    />,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  addItem.mockResolvedValue({ status: 'idle' })
  updateItem.mockResolvedValue({ status: 'idle' })
})

describe('Watchlist deletion confirmation', () => {
  it('names the symbol and requires explicit confirmation before deletion', async () => {
    deleteItem.mockResolvedValue({ message: 'NVDA deleted.', status: 'success', symbol: 'NVDA' })
    renderControls()

    fireEvent.click(screen.getByRole('button', { name: 'Delete NVDA' }))

    const dialog = screen.getByRole('alertdialog', { name: 'Remove NVDA from watchlist?' })
    expect(dialog).toHaveTextContent('This removes NVDA monitoring settings from the paper-research watchlist.')
    expect(deleteItem).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove NVDA' }))

    await waitFor(() => expect(deleteItem).toHaveBeenCalledTimes(1))
    expect(await screen.findByRole('status')).toHaveTextContent('NVDA deleted.')
  })

  it('cancels with Escape without changing settings and restores trigger focus', () => {
    renderControls()
    const trigger = screen.getByRole('button', { name: 'Delete NVDA' })
    const threshold = screen.getByRole('textbox', { name: 'NVDA alert threshold' })
    const dailyResearch = screen.getByRole('checkbox', { name: 'NVDA daily research' })
    const intradayMonitoring = screen.getByRole('checkbox', { name: 'NVDA intraday monitoring' })
    fireEvent.change(threshold, { target: { value: '0.031' } })
    fireEvent.click(dailyResearch)
    fireEvent.click(intradayMonitoring)

    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(threshold).toHaveValue('0.031')
    expect(dailyResearch).not.toBeChecked()
    expect(intradayMonitoring).toBeChecked()
    expect(deleteItem).not.toHaveBeenCalled()
  })

  it('contains keyboard focus and restores it when Cancel closes the confirmation', () => {
    renderControls()
    const trigger = screen.getByRole('button', { name: 'Delete NVDA' })
    fireEvent.click(trigger)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const confirm = screen.getByRole('button', { name: 'Confirm remove NVDA' })

    expect(cancel).toHaveFocus()
    confirm.focus()
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Tab' })
    expect(cancel).toHaveFocus()

    fireEvent.click(cancel)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(deleteItem).not.toHaveBeenCalled()
  })

  it('disables duplicate confirmation while deletion is pending', async () => {
    let settle: ((value: { message: string; status: 'success'; symbol: string }) => void) | undefined
    deleteItem.mockImplementation(() => new Promise((resolve) => { settle = resolve }))
    renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Delete NVDA' }))

    const confirm = screen.getByRole('button', { name: 'Confirm remove NVDA' })
    fireEvent.click(confirm)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Removing NVDA…' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Removing NVDA from watchlist.')
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(screen.getByRole('alertdialog', { name: 'Remove NVDA from watchlist?' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Removing NVDA…' }))

    expect(deleteItem).toHaveBeenCalledTimes(1)
    await act(async () => settle?.({ message: 'NVDA deleted.', status: 'success', symbol: 'NVDA' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  })

  it('announces persistence failure and keeps the confirmation available for retry', async () => {
    deleteItem.mockResolvedValue({
      message: 'Unable to persist watchlist changes. Try again.',
      status: 'error',
      symbol: 'NVDA',
    })
    renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Delete NVDA' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove NVDA' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to persist watchlist changes. Try again.')
    expect(screen.getByRole('alertdialog', { name: 'Remove NVDA from watchlist?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm remove NVDA' })).toBeEnabled()
  })
})
