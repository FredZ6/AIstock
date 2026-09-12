'use client'

import Link from 'next/link'
import { useActionState, useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { useFormStatus } from 'react-dom'

import {
  addWatchlistAction,
  deleteWatchlistAction,
  updateWatchlistAction,
} from '../../app/watchlist/actions'
import type { ApiWatchlistItem } from '../../lib/product-types'
import type { EarningsEvent, MarketBar, MarketQuote } from '../../lib/server/live-data-api'
import { decimalChange, normalizeDecimalSeries } from '../../lib/decimal'
import { formatMoney, formatPercent } from '../../lib/format'
import { formatDualTime, parseAwareInstant } from '../../lib/time'
import {
  initialWatchlistActionState,
  type WatchlistActionState,
} from '../../lib/watchlist-action-state'
import { companyName } from './watchlist-display'
import { Signal } from '../ui/product-ui'

const MAX_VISIBLE_QUOTE_AGE_MS = 24 * 60 * 60 * 1000

function SubmitButton({ label, pendingLabel }: { label: string; pendingLabel: string }) {
  const { pending } = useFormStatus()
  return <button disabled={pending} type="submit">{pending ? pendingLabel : label}</button>
}

function DeleteSubmitButton({ buttonRef, symbol }: { buttonRef: RefObject<HTMLButtonElement | null>; symbol: string }) {
  const { pending } = useFormStatus()
  return <>
    <button className="danger-button" disabled={pending} ref={buttonRef} type="submit">
      {pending ? `Removing ${symbol}…` : `Confirm remove ${symbol}`}
    </button>
    {pending ? <span aria-live="polite" className="sr-only" role="status">Removing {symbol} from watchlist.</span> : null}
  </>
}

function ActionMessage({ state }: { state: WatchlistActionState }) {
  if (state.status === 'idle') return null
  return (
    <p className="watchlist-action-message" data-status={state.status} role={state.status === 'error' ? 'alert' : 'status'}>
      {state.message}
    </p>
  )
}

function AddWatchlistForm() {
  const [state, action] = useActionState(addWatchlistAction, initialWatchlistActionState)
  return (
    <form action={action}>
      <label htmlFor="add-symbol-api">Add symbol</label>
      <input id="add-symbol-api" name="symbol" maxLength={10} autoCapitalize="characters" />
      <input name="daily_research" type="hidden" value="on" />
      <input name="intraday_monitoring" type="hidden" value="on" />
      <SubmitButton label="Add to watchlist" pendingLabel="Adding…" />
      <ActionMessage state={state} />
    </form>
  )
}

function PersistedTrend({ bars, symbol }: { bars: MarketBar[]; symbol: string }) {
  if (bars.length < 2) {
    return <div className="watchlist-trend unavailable-value" aria-label={`${symbol} compact trend`}>Trend unavailable</div>
  }
  const normalized = normalizeDecimalSeries(bars.map((bar) => bar.close))
  const points = normalized.map((value, index) => {
    const x = normalized.length === 1 ? 48 : index * 96 / (normalized.length - 1)
    return `${x},${28 - value * 24}`
  }).join(' ')
  return <div className="watchlist-trend" data-direction={decimalChange(bars.at(-1)!.close, bars[0].close).startsWith('-') ? 'negative' : 'positive'}>
    <svg aria-label={`${symbol} persisted ${bars.length}-session trend`} role="img" viewBox="0 0 96 32">
      <polyline points={points} vectorEffect="non-scaling-stroke" />
    </svg>
  </div>
}

function PersistedSettings({ asOf, earnings, item }: { asOf: string; earnings?: EarningsEvent[]; item: ApiWatchlistItem }) {
  const update = updateWatchlistAction.bind(null, item.symbol)
  const remove = deleteWatchlistAction.bind(null, item.symbol)
  const [updateState, updateAction] = useActionState(update, initialWatchlistActionState)
  const [deleteState, deleteAction, deletePending] = useActionState(
    remove,
    initialWatchlistActionState,
  )
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const deleteTriggerRef = useRef<HTMLButtonElement>(null)
  const cancelDeleteRef = useRef<HTMLButtonElement>(null)
  const confirmDeleteRef = useRef<HTMLButtonElement>(null)
  const nextEarnings = earnings?.find((event) => event.eventDate >= asOf.slice(0, 10))
  const earningsDate = nextEarnings
    ? new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
      .format(new Date(`${nextEarnings.eventDate}T00:00:00Z`))
    : null

  const closeDeleteConfirmation = useCallback(() => {
    if (deletePending) return
    setConfirmingDelete(false)
    deleteTriggerRef.current?.focus()
  }, [deletePending])

  useEffect(() => {
    if (confirmingDelete) cancelDeleteRef.current?.focus()
  }, [confirmingDelete])

  useEffect(() => {
    if (deleteState.status === 'success') closeDeleteConfirmation()
  }, [closeDeleteConfirmation, deleteState.status])

  return (
    <div className="watchlist-api-actions">
      <form action={updateAction} className="watchlist-settings">
        <label>
          <input defaultChecked={item.dailyResearch} name="daily_research" type="checkbox" />
          <span>{item.symbol} daily research</span>
        </label>
        <label>
          <input defaultChecked={item.intradayMonitoring} name="intraday_monitoring" type="checkbox" />
          <span>{item.symbol} intraday monitoring</span>
        </label>
        <label>
          <span>{item.symbol} alert threshold</span>
          <input
            aria-label={`${item.symbol} alert threshold`}
            defaultValue={item.alertThreshold ?? ''}
            inputMode="decimal"
            name="alert_threshold"
          />
        </label>
        <SubmitButton label={`Save ${item.symbol} settings`} pendingLabel={`Saving ${item.symbol}…`} />
        <ActionMessage state={updateState} />
      </form>
      <button
        onClick={() => setConfirmingDelete(true)}
        ref={deleteTriggerRef}
        type="button"
      >
        Delete {item.symbol}
      </button>
      {confirmingDelete ? <div
        aria-labelledby={`delete-${item.symbol}-title`}
        aria-describedby={`delete-${item.symbol}-description`}
        aria-modal="true"
        className="confirmation-backdrop"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !deletePending) {
            event.preventDefault()
            closeDeleteConfirmation()
          }
          if (event.key === 'Tab') {
            const first = cancelDeleteRef.current
            const last = confirmDeleteRef.current
            if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault()
              first?.focus()
            } else if (event.shiftKey && document.activeElement === first) {
              event.preventDefault()
              last?.focus()
            }
          }
        }}
        role="alertdialog"
      >
        <div className="confirmation-dialog">
          <p className="section-kicker">Confirm removal</p>
          <h4 id={`delete-${item.symbol}-title`}>Remove {item.symbol} from watchlist?</h4>
          <p id={`delete-${item.symbol}-description`}>This removes {item.symbol} monitoring settings from the paper-research watchlist.</p>
          <div className="confirmation-actions">
            <button disabled={deletePending} onClick={closeDeleteConfirmation} ref={cancelDeleteRef} type="button">Cancel</button>
            <form action={deleteAction}>
              <DeleteSubmitButton buttonRef={confirmDeleteRef} symbol={item.symbol} />
            </form>
          </div>
        </div>
      </div> : null}
      <ActionMessage state={deleteState} />
      {nextEarnings ? <details className="watchlist-provenance-details">
        <summary>Next earnings {earningsDate}</summary>
        <p>{nextEarnings.provider} · available <time dateTime={nextEarnings.availableAt}>{formatDualTime(nextEarnings.availableAt).newYork}</time></p>
        <code>{nextEarnings.rawObjectKey}</code>
        <small>{nextEarnings.contentHash}</small>
      </details> : earnings ? <p className="watchlist-setting-note">No persisted upcoming earnings at this cutoff</p> : <p className="watchlist-setting-note">Earnings schedule unavailable</p>}
    </div>
  )
}

export function WatchlistApiControls({
  asOf,
  earningsBySymbol = {},
  historiesBySymbol = {},
  items,
  quotes,
}: {
  asOf: string
  earningsBySymbol?: Record<string, EarningsEvent[]>
  historiesBySymbol?: Record<string, MarketBar[]>
  items: ApiWatchlistItem[]
  quotes: MarketQuote[]
}) {
  const quoteBySymbol = new Map(quotes.map((quote) => [quote.symbol, quote]))
  return (
    <section className="terminal-section first-section" aria-labelledby="watchlist-api-count">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Persisted research universe</p>
          <h2 id="watchlist-api-count">{items.length} symbols</h2>
        </div>
        <span className="muted-copy">PostgreSQL configuration · paper trading only</span>
      </div>
      <ol className="ranked-watchlist" aria-label="Ranked research watchlist">
        {items.map((item, index) => {
          const quote = quoteBySymbol.get(item.symbol)
          const history = historiesBySymbol[item.symbol] ?? []
          const latestBar = history.at(-1)
          const previousBar = history.at(-2)
          const dailyChange = latestBar && previousBar ? decimalChange(latestBar.close, previousBar.close) : null
          const historyIsStale = latestBar
            ? parseAwareInstant(asOf).getTime() - parseAwareInstant(latestBar.availableAt).getTime() > MAX_VISIBLE_QUOTE_AGE_MS
            : false
          const quoteIsStale = quote
            ? parseAwareInstant(asOf).getTime() - parseAwareInstant(quote.availableAt).getTime() > MAX_VISIBLE_QUOTE_AGE_MS
            : false
          return <li key={item.symbol}>
            <span className="watchlist-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <div className="watchlist-identity">
              <Link href={`/research/${item.symbol}`}>{item.symbol}</Link>
              <span>{companyName(item.symbol)}</span>
            </div>
            <PersistedTrend bars={history} symbol={item.symbol} />
            <div className="watchlist-quote">
              <strong className={quote ? undefined : 'unavailable-value'}>{quote ? formatMoney(quote.close, 'USD') : 'Price unavailable'}</strong>
              <span className={dailyChange ? undefined : 'unavailable-value'}>{dailyChange ? formatPercent(dailyChange) : 'Change unavailable'}</span>
            </div>
            <div className="watchlist-provenance">
              <span>{quote ? `${quote.provider} · ${quote.coverage}` : 'Quality unavailable'}</span>
              {quoteIsStale ? <Signal tone="stale">STALE</Signal> : null}
              {quote
                ? <time dateTime={quote.availableAt}>Persisted {formatDualTime(quote.availableAt).newYork}</time>
                : <span className="unavailable-value">Persistence time unavailable</span>}
              {quoteIsStale ? <span>Quote older than 24 hours at snapshot</span> : null}
              {historyIsStale ? <Signal tone="stale">TREND STALE</Signal> : null}
              {historyIsStale ? <span>Historical trend older than 24 hours at snapshot</span> : null}
              {latestBar ? <details className="watchlist-provenance-details">
                <summary>PIT cutoff {formatDualTime(asOf).newYork}</summary>
                <span>Bar event <time dateTime={latestBar.eventTime}>{formatDualTime(latestBar.eventTime).newYork}</time></span>
                <span>Available <time dateTime={latestBar.availableAt}>{formatDualTime(latestBar.availableAt).newYork}</time></span>
                <code>{latestBar.rawObjectKey}</code>
                <small>{latestBar.contentHash}</small>
              </details> : null}
            </div>
          </li>
        })}
      </ol>
      <section className="watchlist-configuration" aria-labelledby="watchlist-configuration-title">
        <div className="section-heading">
          <div><p className="section-kicker">Configure</p><h3 id="watchlist-configuration-title">Watchlist configuration</h3></div>
          <span className="muted-copy">Changes are confirmed by FastAPI before refresh.</span>
        </div>
        <div className="watchlist-controls"><AddWatchlistForm /></div>
        <div className="watchlist-config-list">
          {items.map((item) => <section aria-label={`${item.symbol} settings`} key={item.symbol}>
            <details>
              <summary>{item.symbol} settings</summary>
              <PersistedSettings asOf={asOf} earnings={earningsBySymbol[item.symbol]} item={item} />
            </details>
          </section>)}
        </div>
      </section>
    </section>
  )
}
