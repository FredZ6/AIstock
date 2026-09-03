import { AppShell } from '../components/layout/app-shell'
import { StateBoundary } from '../components/states/state-boundary'

export default function Loading() {
  return (
    <AppShell currentPath="/">
      <StateBoundary state={{ kind: 'loading', label: 'persisted data' }} />
    </AppShell>
  )
}
