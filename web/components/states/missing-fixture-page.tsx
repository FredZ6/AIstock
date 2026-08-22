import Link from 'next/link'

import { AppShell } from '../layout/app-shell'
import { StateBoundary } from './state-boundary'

type MissingFixturePageProps = {
  currentPath: string
  entity: string
  returnHref: string
  returnLabel: string
}

export function MissingFixturePage({ currentPath, entity, returnHref, returnLabel }: MissingFixturePageProps) {
  return (
    <AppShell currentPath={currentPath}>
      <header className="today-heading page-heading">
        <div><p className="eyebrow">Fixture boundary</p><h1>{entity}</h1><p className="today-summary">No frozen detail is available for this identifier.</p></div>
      </header>
      <div className="missing-fixture-state">
        <StateBoundary state={{ kind: 'empty', title: 'Frozen fixture unavailable', message: 'The interface will not substitute another symbol or run. Connect a read-only provider later, or choose an available frozen fixture.' }} />
        <Link href={returnHref}>{returnLabel}</Link>
      </div>
    </AppShell>
  )
}
