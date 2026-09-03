import { AlertsPage } from '../../components/alerts/alerts-page'
import { ApiCollectionPage, ApiFailurePage } from '../../components/live/api-pages'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { getAlerts } from '../../lib/server/live-data-api'

export const dynamic = 'force-dynamic'

export default async function AlertsRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureAlertsSnapshot } = await import('../../lib/fixtures')
      return <AlertsPage snapshot={fixtureAlertsSnapshot} />
    }
    const asOf = new Date().toISOString()
    const page = await getAlerts({ baseUrl: config.baseUrl, decisionTime: asOf })
    return <ApiCollectionPage asOf={asOf} count={page.items.length} currentPath="/alerts" emptyTitle="No persisted alerts" title="Alerts" />
  } catch (error) {
    reportLiveDataFailure('/alerts', 'alerts', error)
    return <ApiFailurePage currentPath="/alerts" title="Alerts" />
  }
}
