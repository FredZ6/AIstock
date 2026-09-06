export type ResearchRunActionState = {
  message: string
  runId: string | null
  status: 'idle' | 'error' | 'success'
  symbol: string
}

export const initialResearchRunActionState: ResearchRunActionState = {
  message: '',
  runId: null,
  status: 'idle',
  symbol: '',
}
