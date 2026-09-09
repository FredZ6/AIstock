'use client'

import Link from 'next/link'
import { useActionState } from 'react'
import { useFormStatus } from 'react-dom'

import {
  addWatchlistAction,
  deleteWatchlistAction,
  updateWatchlistAction,
} from '../../app/watchlist/actions'
import type { ApiWatchlistItem } from '../../lib/product-types'
import type { MarketQuote } from '../../lib/server/live-data-api'
import { formatMoney } from '../../lib/format'
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

function PersistedSettings({ item }: { item: ApiWatchlistItem }) {
  const update = updateWatchlistAction.bind(null, item.symbol)
  const remove = deleteWatchlistAction.bind(null, item.symbol)
  const [updateState, updateAction] = useActionState(update, initialWatchlistActionState)
  const [deleteState, deleteAction] = useActionState(remove, initialWatchlistActionState)

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
      <form action={deleteAction}>
        <SubmitButton label={`Delete ${item.symbol}`} pendingLabel={`Deleting ${item.symbol}…`} />
        <ActionMessage state={deleteState} />
      </form>
      <p className="watchlist-setting-note">Earnings schedule unavailable</p>
    </div>
  )
}

export function WatchlistApiControls({ asOf, items, quotes }: { asOf: string; items: ApiWatchlistItem[]; quotes: MarketQuote[] }) {
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
          const quoteIsStale = quote
            ? parseAwareInstant(asOf).getTime() - parseAwareInstant(quote.availableAt).getTime() > MAX_VISIBLE_QUOTE_AGE_MS
            : false
          return <li key={item.symbol}>
            <span className="watchlist-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <div className="watchlist-identity">
              <Link href={`/research/${item.symbol}`}>{item.symbol}</Link>
              <span>{companyName(item.symbol)}</span>
            </div>
            <div className="watchlist-trend unavailable-value" aria-label={`${item.symbol} compact trend`}>Trend unavailable</div>
            <div className="watchlist-quote">
              <strong className={quote ? undefined : 'unavailable-value'}>{quote ? formatMoney(quote.close, 'USD') : 'Price unavailable'}</strong>
              <span className="unavailable-value">Change unavailable</span>
            </div>
            <div className="watchlist-provenance">
              <span>{quote ? `${quote.provider} · ${quote.coverage}` : 'Quality unavailable'}</span>
              {quoteIsStale ? <Signal tone="stale">STALE</Signal> : null}
              {quote
                ? <time dateTime={quote.availableAt}>Persisted {formatDualTime(quote.availableAt).newYork}</time>
                : <span className="unavailable-value">Persistence time unavailable</span>}
              {quoteIsStale ? <span>Quote older than 24 hours at snapshot</span> : null}
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
              <PersistedSettings item={item} />
            </details>
          </section>)}
        </div>
      </section>
    </section>
  )
}
