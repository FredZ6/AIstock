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
import {
  initialWatchlistActionState,
  type WatchlistActionState,
} from '../../lib/watchlist-action-state'

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
    </div>
  )
}

export function WatchlistApiControls({ items, quotes }: { items: ApiWatchlistItem[]; quotes: MarketQuote[] }) {
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
      <section className="watchlist-controls" aria-labelledby="watchlist-api-controls-title">
        <div>
          <h3 id="watchlist-api-controls-title">Watchlist controls</h3>
          <p>Changes are confirmed by FastAPI before this page refreshes.</p>
        </div>
        <AddWatchlistForm />
      </section>
      <div className="table-scroll">
        <table aria-label="Persisted research watchlist">
          <thead>
            <tr><th scope="col">Symbol</th><th scope="col">Price</th><th scope="col">Day</th><th scope="col">Research opinion</th><th scope="col">Portfolio action</th><th scope="col">Next earnings</th><th scope="col">Monitoring</th><th scope="col">Last research</th><th scope="col">Data quality</th></tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const quote = quoteBySymbol.get(item.symbol)
              return <tr key={item.symbol}>
                <th scope="row"><Link href={`/research/${item.symbol}`}>{item.symbol}</Link></th>
                <td className={quote ? undefined : 'unavailable-value'}>{quote ? formatMoney(quote.close, 'USD') : 'Unavailable'}</td>
                <td className="unavailable-value">Unavailable</td>
                <td className="unavailable-value">Unavailable</td>
                <td className="unavailable-value">Unavailable</td>
                <td className="unavailable-value">Unavailable</td>
                <td><PersistedSettings item={item} /></td>
                <td className="unavailable-value">Unavailable</td>
                <td>{quote ? `${quote.provider} · ${quote.coverage}` : <span className="unavailable-value">Unavailable</span>}</td>
              </tr>
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
