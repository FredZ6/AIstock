import Link from 'next/link'
import type { ReactNode } from 'react'

type LoadingState = {
  kind: 'loading'
  label: string
}

type MessageState = {
  message: string
  title: string
}

type EmptyState = MessageState & {
  kind: 'empty'
}

type StaleState = MessageState & {
  kind: 'stale'
  lastUpdatedAt: string
}

type DegradedState = MessageState & {
  kind: 'degraded'
  providers: string[]
}

type PartialState = MessageState & {
  kind: 'partial'
  missing: string[]
}

type FailureState = MessageState & {
  kind: 'failure'
  retryHref?: string
}

type SuccessState = {
  kind: 'success'
}

export type ViewState =
  | LoadingState
  | EmptyState
  | StaleState
  | DegradedState
  | PartialState
  | FailureState
  | SuccessState

type StateBoundaryProps = {
  children?: ReactNode
  compact?: boolean
  state: ViewState
}

function StateMessage({ compact, state }: { compact?: boolean; state: EmptyState | StaleState | DegradedState | PartialState }) {
  return (
    <section
      aria-label={state.title}
      aria-live="polite"
      className={`state-surface surface-card${compact ? ' state-compact' : ''}`}
      data-state={state.kind}
      role="status"
    >
      <p className="state-label">
        {state.kind}
      </p>
      <h2>{state.title}</h2>
      <p className="state-message">{state.message}</p>
      {state.kind === 'stale' ? (
        <p className="state-timestamp">
          Last updated <time dateTime={state.lastUpdatedAt}>{state.lastUpdatedAt}</time>
        </p>
      ) : null}
      {state.kind === 'degraded' ? (
        <ul aria-label="Degraded providers" className="state-tags">
          {state.providers.map((provider) => (
            <li key={provider}>
              {provider}
            </li>
          ))}
        </ul>
      ) : null}
      {state.kind === 'partial' ? (
        <ul aria-label="Missing records" className="state-tags">
          {state.missing.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
    </section>
  )
}

export function StateBoundary({ children, compact, state }: StateBoundaryProps) {
  if (state.kind === 'success') {
    return children
  }

  if (state.kind === 'loading') {
    return (
      <section
        aria-live="polite"
        className={`state-surface surface-card${compact ? ' state-compact' : ''}`}
        data-state="loading"
        role="status"
      >
        <p className="state-message">Loading {state.label}…</p>
      </section>
    )
  }

  if (state.kind === 'failure') {
    return (
      <section
        aria-label={state.title}
        className={`state-surface surface-card${compact ? ' state-compact' : ''}`}
        data-state="failure"
        role="alert"
      >
        <p className="state-label">Failure</p>
        <h2>{state.title}</h2>
        <p className="state-message">{state.message}</p>
        {state.retryHref ? (
          <Link className="state-retry" href={state.retryHref}>
            Try again
          </Link>
        ) : null}
      </section>
    )
  }

  return (
    <>
      <StateMessage compact={compact} state={state} />
      {state.kind === 'degraded' || state.kind === 'partial' ? children : null}
    </>
  )
}
