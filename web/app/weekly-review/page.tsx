import { WeeklyReviewPage } from '../../components/learning/weekly-review-page'
import { ApiCollectionPage, ApiFailurePage, ApiWeeklyReviewPage } from '../../components/live/api-pages'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { getWeeklyReviewDetail, getWeeklyReviews } from '../../lib/server/live-data-api'

export const dynamic = 'force-dynamic'

export default async function WeeklyReviewRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureWeeklyReviewSnapshot } = await import('../../lib/fixtures')
      return <WeeklyReviewPage snapshot={fixtureWeeklyReviewSnapshot} />
    }
    const asOf = new Date().toISOString()
    const page = await getWeeklyReviews({ baseUrl: config.baseUrl, decisionTime: asOf })
    const latest = page.items[0]
    if (!latest) return <ApiCollectionPage asOf={asOf} count={0} currentPath="/weekly-review" emptyTitle="No persisted weekly reviews" title="Weekly Review" />
    if (typeof latest.id !== 'string') throw new TypeError('Weekly review id is invalid')
    const detail = await getWeeklyReviewDetail({ baseUrl: config.baseUrl, decisionTime: asOf }, latest.id)
    return <ApiWeeklyReviewPage asOf={asOf} detail={detail} />
  } catch (error) {
    reportLiveDataFailure('/weekly-review', 'weekly-reviews', error)
    return <ApiFailurePage currentPath="/weekly-review" title="Weekly Review" />
  }
}
