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
  | FailureState
  | SuccessState

type StateBoundaryProps = {
  children?: ReactNode
  state: ViewState
}

function StateMessage({ state }: { state: EmptyState | StaleState | DegradedState }) {
  return (
    <section
      aria-label={state.title}
      aria-live="polite"
      className="state-surface border-y border-zinc-700 bg-zinc-900/70 px-5 py-6"
      data-state={state.kind}
      role="status"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-300">
        {state.kind}
      </p>
      <h2 className="mt-2 text-lg font-semibold text-zinc-100">{state.title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">{state.message}</p>
      {state.kind === 'stale' ? (
        <p className="mt-4 text-xs text-zinc-500">
          Last updated <time dateTime={state.lastUpdatedAt}>{state.lastUpdatedAt}</time>
        </p>
      ) : null}
      {state.kind === 'degraded' ? (
        <ul aria-label="Degraded providers" className="mt-4 flex flex-wrap gap-2">
          {state.providers.map((provider) => (
            <li className="border border-amber-400/40 px-2 py-1 text-xs text-amber-200" key={provider}>
              {provider}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

export function StateBoundary({ children, state }: StateBoundaryProps) {
  if (state.kind === 'success') {
    return children
  }

  if (state.kind === 'loading') {
    return (
      <section
        aria-live="polite"
        className="state-surface border-y border-zinc-800 px-5 py-6"
        data-state="loading"
        role="status"
      >
        <p className="text-sm text-zinc-300">Loading {state.label}…</p>
      </section>
    )
  }

  if (state.kind === 'failure') {
    return (
      <section
        aria-label={state.title}
        className="state-surface border-y border-red-400/40 bg-red-950/20 px-5 py-6"
        data-state="failure"
        role="alert"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-red-300">Failure</p>
        <h2 className="mt-2 text-lg font-semibold text-zinc-100">{state.title}</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">{state.message}</p>
        {state.retryHref ? (
          <Link className="mt-4 inline-block text-sm font-semibold text-red-200 underline" href={state.retryHref}>
            Try again
          </Link>
        ) : null}
      </section>
    )
  }

  return (
    <>
      <StateMessage state={state} />
      {state.kind === 'degraded' ? children : null}
    </>
  )
}
