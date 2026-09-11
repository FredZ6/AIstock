'use client'

import { useDeferredValue, useMemo, useState } from 'react'

import { formatDecimal } from '../../lib/format'
import type { FinancialFact, SecFiling } from '../../lib/server/live-data-api'
import { formatDualTime } from '../../lib/time'

function includes(value: string | null | undefined, query: string) {
  return value?.toLocaleLowerCase().includes(query) ?? false
}

function concept(fact: FinancialFact) {
  return fact.canonicalConcept ?? fact.sourceConcept
}

function factCategory(fact: FinancialFact) {
  return fact.canonicalConcept ?? 'UNMAPPED'
}

function newestFacts(facts: FinancialFact[]) {
  const newest = new Map<string, FinancialFact>()
  for (const fact of facts) {
    const key = concept(fact)
    const current = newest.get(key)
    if (!current
      || fact.periodEnd > current.periodEnd
      || (fact.periodEnd === current.periodEnd && fact.periodStart > current.periodStart)
      || (fact.periodEnd === current.periodEnd && fact.periodStart === current.periodStart && fact.availableAt > current.availableAt)
      || (fact.periodEnd === current.periodEnd && fact.periodStart === current.periodStart && fact.availableAt === current.availableAt && fact.id > current.id)
    ) newest.set(key, fact)
  }
  return [...newest.values()].sort((left, right) => concept(left).localeCompare(concept(right)))
}

export function SecFilingsDisclosure({ filings }: { filings: SecFiling[] }) {
  const [search, setSearch] = useState('')
  const query = useDeferredValue(search.trim().toLocaleLowerCase())
  const visible = useMemo(() => filings.filter((filing) => !query || [
    filing.id,
    filing.provider,
    filing.form,
    filing.description,
    filing.accessionNumber,
    filing.filingDate,
    filing.reportDate,
    filing.documentRawObjectKey,
  ].some((value) => includes(value, query))), [filings, query])

  return <details className="terminal-section research-disclosure">
    <summary>SEC filings · {filings.length}</summary>
    <h2>SEC filings</h2>
    <div className="evidence-toolbar">
      <label>Search filings<input aria-label="Search SEC filings" type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <span aria-live="polite">{visible.length} of {filings.length} filings</span>
    </div>
    {visible.length ? <div className="table-scroll" tabIndex={0}><table aria-label="Persisted SEC filings"><thead><tr><th>Form</th><th>Filed</th><th>Report period</th><th>Accession</th><th>Record ID</th><th>Available</th><th>Raw source</th></tr></thead><tbody>
      {visible.map((filing) => <tr key={filing.id}><td>{filing.form}</td><td>{filing.filingDate}</td><td>{filing.reportDate ?? 'Unavailable'}</td><td>{filing.accessionNumber}</td><td><code>{filing.id}</code></td><td>{formatDualTime(filing.availableAt).newYork}</td><td><code>{filing.documentRawObjectKey}</code></td></tr>)}
    </tbody></table></div> : <div aria-label="No SEC filings match active search" className="evidence-empty" role="status">
      <p>No SEC filings match search “{search}”.</p>
      <button type="button" onClick={() => setSearch('')}>Reset SEC filing search</button>
    </div>}
  </details>
}

export function FinancialFactsDisclosure({ facts, filings }: { facts: FinancialFact[]; filings: SecFiling[] }) {
  const [category, setCategory] = useState('ALL')
  const [period, setPeriod] = useState('ALL')
  const [search, setSearch] = useState('')
  const query = useDeferredValue(search.trim().toLocaleLowerCase())
  const categories = useMemo(() => [...new Set(facts.map(factCategory))].sort(), [facts])
  const periods = useMemo(() => [...new Set(facts.map((fact) => fact.periodEnd))].sort().reverse(), [facts])
  const latest = useMemo(() => newestFacts(facts.filter((fact) => fact.canonicalConcept !== null)), [facts])
  const rawSourceByAccession = useMemo(() => new Map(
    filings.map((filing) => [filing.accessionNumber, filing.documentRawObjectKey]),
  ), [filings])
  const visible = useMemo(() => facts.filter((fact) => (
    (category === 'ALL' || category === fact.canonicalConcept || (category === 'UNMAPPED' && fact.canonicalConcept === null))
    && (period === 'ALL' || fact.periodEnd === period)
    && (!query || [
      fact.id,
      fact.provider,
      fact.taxonomy,
      fact.sourceConcept,
      fact.canonicalConcept,
      fact.accessionNumber,
      fact.periodStart,
      fact.periodEnd,
      fact.mappingStatus,
    ].some((value) => includes(value, query)))
  )), [category, facts, period, query])
  const reset = () => {
    setCategory('ALL')
    setPeriod('ALL')
    setSearch('')
  }

  return <details className="terminal-section research-disclosure">
    <summary>Financial facts · {facts.length}</summary>
    <h2>Financial facts</h2>
    <section aria-label="Newest persisted values" className="newest-facts">
      <div className="section-heading"><h3>Newest persisted values</h3><span>{latest.length} concepts</span></div>
      <dl>{latest.map((fact) => <div key={concept(fact)}><dt>{concept(fact)}</dt><dd>{formatDecimal(fact.value)} {fact.currency ?? fact.unit}</dd><small>{fact.periodStart} — {fact.periodEnd}</small></div>)}</dl>
    </section>
    <div className="evidence-toolbar evidence-toolbar-facts">
      <label>Search facts<input aria-label="Search financial facts" type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Category<select aria-label="Financial fact category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="ALL">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Reporting period<select aria-label="Financial fact period" value={period} onChange={(event) => setPeriod(event.target.value)}><option value="ALL">All periods</option>{periods.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <span aria-live="polite">{visible.length} of {facts.length} facts</span>
    </div>
    {visible.length ? <div className="table-scroll" tabIndex={0}><table aria-label="Persisted financial facts"><thead><tr><th>Concept</th><th>Source concept</th><th>Value</th><th>Period</th><th>Mapping</th><th>Accession</th><th>Fact ID</th><th>Available</th><th>Raw source</th></tr></thead><tbody>
      {visible.map((fact) => <tr key={fact.id}><td>{concept(fact)}</td><td>{fact.sourceConcept}<small>{fact.taxonomy}</small></td><td>{formatDecimal(fact.value)} {fact.currency ?? fact.unit}</td><td>{fact.periodStart} — {fact.periodEnd}</td><td>{fact.mappingStatus}</td><td>{fact.accessionNumber}</td><td><code>{fact.id}</code></td><td>{formatDualTime(fact.availableAt).newYork}</td><td><code>{rawSourceByAccession.get(fact.accessionNumber) ?? 'Unavailable'}</code></td></tr>)}
    </tbody></table></div> : <div aria-label="No financial facts match active filters" className="evidence-empty" role="status">
      <p>No financial facts match {[
        search ? `search “${search}”` : null,
        category !== 'ALL' ? `category ${category}` : null,
        period !== 'ALL' ? `period ${period}` : null,
      ].filter(Boolean).join(', ')}.</p>
      <button type="button" onClick={reset}>Reset financial fact filters</button>
    </div>}
  </details>
}
