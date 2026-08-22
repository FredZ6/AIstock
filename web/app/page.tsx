import { TodayPage } from '../components/today-page'
import { fixtureTodaySnapshot } from '../lib/api'

export default function Home() {
  return <TodayPage snapshot={fixtureTodaySnapshot} />
}
