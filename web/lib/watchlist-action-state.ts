export type WatchlistActionState = {
  message?: string
  status: 'error' | 'idle' | 'success'
  symbol?: string
}

export const initialWatchlistActionState: WatchlistActionState = { status: 'idle' }
