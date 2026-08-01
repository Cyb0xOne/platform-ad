import { createRoot } from 'react-dom/client'
import { useState } from 'react'

import { useDashboardData } from './data/useDashboardData'
import { OperationsShell } from './shared/shell'
import { WarRoomHeaderStatus, WarRoomWorkspace } from './war-room/WarRoom'
import './styles.css'
import './war-room/war-room.css'

const railItems = [
  { icon: 'overview', label: 'Overview', viewId: 'overview' },
  { icon: 'matrix', label: 'Matrix', viewId: 'matrix' },
  { icon: 'pulse', label: 'Timeline', viewId: 'timeline' },
] as const

const workspaceViews = [
  {
    id: 'overview',
    label: 'Overview',
    title: 'Operational overview',
    description: 'The shared public workspace is ready for read-only game telemetry without implying that a live source is connected.',
    regions: ['Game status header', 'Scoreboard field', 'Attack activity feed'],
  },
  {
    id: 'matrix',
    label: 'Matrix',
    title: 'Service status matrix',
    description: 'This region will hold the dense team-by-service health view in a later parity task.',
    regions: ['Team index', 'Service columns', 'Status detail context'],
  },
  {
    id: 'timeline',
    label: 'Timeline',
    title: 'Round timeline',
    description: 'Historical score and event visualization remains intentionally unimplemented in this foundation.',
    regions: ['Round axis', 'Team series', 'Event annotations'],
  },
] as const

function NextDashboard() {
  const dashboard = useDashboardData()
  const [activeView, setActiveView] = useState('overview')

  return (
    <OperationsShell
      activeView={activeView}
      appName="A/D War Room"
      defaultView="overview"
      description="Projector-ready public telemetry surface"
      eyebrow="Attack-Defense // Public display"
      footer={(
        <>
          <span>A/D War Room</span>
          <span>Public telemetry</span>
          <span>{dashboard.stale ? 'Reconnecting' : dashboard.loading ? 'Waiting for source' : 'Read-only sync'}</span>
        </>
      )}
      headerStatus={<WarRoomHeaderStatus dashboard={dashboard} />}
      inspector={null}
      mode="public"
      navItems={railItems}
      networkLabel="Read only"
      onViewChange={setActiveView}
      pageHeading="Next dashboard"
      title="War Room overview"
      views={workspaceViews}
      workspace={(
        <WarRoomWorkspace
          activeView={activeView}
          dashboard={dashboard}
          onViewChange={setActiveView}
          views={workspaceViews}
        />
      )}
    />
  )
}

createRoot(document.getElementById('root')!).render(<NextDashboard />)
