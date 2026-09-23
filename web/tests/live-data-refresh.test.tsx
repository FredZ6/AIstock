import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}))

import { LiveDataRefresh } from '../components/live/live-data-refresh'

afterEach(() => {
  vi.useRealTimers()
  refresh.mockReset()
  vi.restoreAllMocks()
})

describe('LiveDataRefresh', () => {
  it('refreshes visible API pages once every 60 seconds', () => {
    vi.useFakeTimers()
    render(<LiveDataRefresh />)

    act(() => vi.advanceTimersByTime(59_999))
    expect(refresh).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(1))
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('does not refresh a hidden page', () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    render(<LiveDataRefresh />)

    act(() => vi.advanceTimersByTime(60_000))

    expect(refresh).not.toHaveBeenCalled()
  })

  it('does not refresh while the browser is offline', () => {
    vi.useFakeTimers()
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    render(<LiveDataRefresh />)

    act(() => vi.advanceTimersByTime(60_000))

    expect(refresh).not.toHaveBeenCalled()
  })

  it('stops refreshing after unmount', () => {
    vi.useFakeTimers()
    const { unmount } = render(<LiveDataRefresh />)

    unmount()
    act(() => vi.advanceTimersByTime(60_000))

    expect(refresh).not.toHaveBeenCalled()
  })
})
