import { Tabs } from '@base-ui/react/tabs'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import type {
  Attack,
  FirstBlood,
  Game,
  Scoreboard,
  ScoreboardTeam,
  TimelinePoint,
} from '../data/contracts'
import { formatCompactNumber, formatLocalTime, formatNumber } from '../data/formatters'
import type { DashboardState, ResourceState } from '../data/polling'
import { Readout, StatusLegend, type WorkspaceView } from '../shared/shell'
import {
  ATTACK_FRESHNESS_MS,
  attackIdentityKey,
  filterAttackFeed,
  getDefenseTeam,
  updateAttackFreshness,
  type AttackFreshnessTracker,
  type FeedMode,
} from './attacks'
import { normalizeStatus, summarizeTeam, type ServiceStatus } from './status'
import { groupTimelineSeries, scaleTimelineSeries } from './timeline'
import { WarRoomInspector } from './WarRoomInspector'
import type { WarRoomSelection } from './selection'

const chartDimensions = { width: 1_000, height: 320, inset: 48 }

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => (
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ))

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return reduced
}

function useRoundClock(game: Game | null) {
  const reducedMotion = useReducedMotion()
  const observedRound = useRef<number | null>(null)
  const [transition, setTransition] = useState<{
    startedAt: number
    durationMs: number
  } | null>(null)
  const [now, setNow] = useState(Date.now)

  useEffect(() => {
    if (game === null) return
    if (observedRound.current === null) {
      observedRound.current = game.real_round
      return
    }
    if (observedRound.current !== game.real_round) {
      observedRound.current = game.real_round
      const startedAt = Date.now()
      setNow(startedAt)
      setTransition({ startedAt, durationMs: Math.max(1, game.round_time * 1_000) })
    }
  }, [game])

  useEffect(() => {
    if (transition === null || !game?.game_running) return
    const timer = window.setInterval(() => setNow(Date.now()), reducedMotion ? 1_000 : 250)
    return () => window.clearInterval(timer)
  }, [game?.game_running, reducedMotion, transition])

  if (transition === null) return { progress: null, remainingSeconds: null }
  const elapsed = Math.max(0, now - transition.startedAt)
  const progress = Math.min(1, elapsed / transition.durationMs)
  return {
    progress,
    remainingSeconds: Math.max(0, Math.ceil((transition.durationMs - elapsed) / 1_000)),
  }
}

function formatRound(round: number | null | undefined) {
  if (round === null || round === undefined) return '---'
  return formatNumber(round).padStart(3, '0')
}

function resourceState<T>(resource: ResourceState<T>) {
  if (resource.data === null) return resource.error === null ? 'waiting' : 'error'
  return resource.error === null ? 'ready' : 'stale'
}

function RegionStatus<T>({ resource }: { resource: ResourceState<T> }) {
  const state = resourceState(resource)
  const label = state === 'ready' ? 'SYNC' : state === 'waiting' ? 'WAITING' : state === 'stale' ? 'STALE' : 'RECONNECT'
  return <span className={`region-status region-status--${state}`}>{label}</span>
}

function ResourceMessage<T>({
  resource,
  waiting,
  error,
}: {
  resource: ResourceState<T>
  waiting: string
  error: string
}) {
  if (resource.data !== null) {
    if (resource.error === null) return null
    return (
      <p className="region-message region-message--stale" role="status">
        Last-good data · updated {formatLocalTime(resource.lastUpdated)}
      </p>
    )
  }

  return (
    <div className={`region-empty region-empty--${resource.error === null ? 'waiting' : 'error'}`}>
      <strong>{resource.error === null ? waiting : error}</strong>
      <span>{resource.error === null ? 'Polling public telemetry…' : 'Reconnecting automatically; no successful response yet.'}</span>
    </div>
  )
}

function Region({
  children,
  kicker,
  resource,
  title,
}: {
  children: ReactNode
  kicker: string
  resource: ResourceState<unknown>
  title: string
}) {
  return (
    <section className="war-region" aria-labelledby={`${kicker}-title`}>
      <header className="war-region__header">
        <div>
          <span>{kicker}</span>
          <h2 id={`${kicker}-title`}>{title}</h2>
        </div>
        <RegionStatus resource={resource} />
      </header>
      {children}
    </section>
  )
}

export function WarRoomHeaderStatus({ dashboard }: { dashboard: DashboardState }) {
  const resources = [dashboard.game, dashboard.scoreboard, dashboard.attacks, dashboard.timeline, dashboard.firstBlood]
  const hasData = resources.some((resource) => resource.data !== null)
  const hasError = resources.some((resource) => resource.error !== null)
  const game = dashboard.game.data
  const clock = useRoundClock(game)
  const gameLabel = game === null ? 'WAITING' : game.game_running ? 'LIVE' : 'PAUSED'
  const syncLabel = !hasData && dashboard.loading ? 'WAITING' : hasError ? 'RECONNECT' : 'SYNC'

  return (
    <div aria-label="Application status" className="header-status war-header-status">
      <Readout label="Game" status={game?.game_running ? 'up' : 'na'} value={gameLabel} />
      <Readout label="Round" value={formatRound(game?.real_round)} />
      <Readout label="Channel" status={hasError ? 'error' : hasData ? 'up' : 'na'} value={syncLabel} />
      <div className="round-progress">
        <span>Round window</span>
        <progress aria-label="Observed round progress" max={1} value={clock.progress ?? undefined} />
        <strong>{clock.remainingSeconds === null ? 'INDETERMINATE' : `${formatNumber(clock.remainingSeconds)}s`}</strong>
      </div>
      <span className="network-label">Read only</span>
    </div>
  )
}

type InspectorTarget = Exclude<WarRoomSelection, null>
type OpenInspector = (selection: InspectorTarget, triggerId: string) => void

function TeamCard({
  onOpenInspector,
  selected,
  team,
}: {
  onOpenInspector: OpenInspector
  selected: boolean
  team: ScoreboardTeam
}) {
  const summary = summarizeTeam(team)
  const teamKey = team.team.trim().toLowerCase()
  const accent = teamKey === 'athena' || teamKey === 'ares' ? ` team-card--${teamKey}` : ''
  const triggerId = `war-team-card-${team.team_id}`

  return (
    <button
      aria-expanded={selected}
      aria-haspopup="dialog"
      aria-label={`Inspect team ${team.team}`}
      className={`team-card${accent}${team.highlighted ? ' team-card--highlighted' : ''}`}
      id={triggerId}
      onClick={() => onOpenInspector({ kind: 'team', teamId: team.team_id }, triggerId)}
      type="button"
    >
      <span className="team-card__header">
        <span className="team-card__rank">#{formatNumber(team.pos).padStart(2, '0')}</span>
        <span>
          <span className="team-card__name">{team.team}</span>
          {team.highlighted && <span className="team-card__marker">TIM KITA</span>}
        </span>
        <strong className="team-card__total">{formatNumber(summary.total)}</strong>
      </span>
      <span className="team-metrics">
        <span><span>UP</span><strong>{formatNumber(summary.upCount)} / {formatNumber(summary.serviceCount)}</strong></span>
        <span><span>Mean SLA</span><strong>{formatNumber(summary.meanSla)}%</strong></span>
        <span><span>Stolen</span><strong>{formatNumber(summary.stolen)}</strong></span>
        <span><span>Lost</span><strong>{formatNumber(summary.lost)}</strong></span>
      </span>
    </button>
  )
}

function ScoreboardRegion({
  onOpenInspector,
  resource,
  selection,
}: {
  onOpenInspector: OpenInspector
  resource: ResourceState<Scoreboard>
  selection: WarRoomSelection
}) {
  return (
    <Region kicker="scoreboard" resource={resource} title="Scoreboard">
      <ResourceMessage resource={resource} waiting="Waiting for ranked teams" error="Scoreboard unavailable" />
      {resource.data !== null && (
        resource.data.teams.length === 0
          ? <div className="region-empty"><strong>No ranked teams yet</strong><span>Scores will appear after the first game data is recorded.</span></div>
          : <div className="scoreboard-grid">{resource.data.teams.map((team) => (
            <TeamCard
              key={team.team_id}
              onOpenInspector={onOpenInspector}
              selected={selection?.kind === 'team' && selection.teamId === team.team_id}
              team={team}
            />
          ))}</div>
      )}
    </Region>
  )
}

function statusClass(status: ServiceStatus) {
  return status.toLowerCase().replace('/', '')
}

function FirstBloodLabel({ firstBlood, taskId }: { firstBlood: FirstBlood | null; taskId: number }) {
  const entry = firstBlood?.[`${taskId}`]
  if (!entry) return <small>First blood —</small>
  return <small title={formatLocalTime(entry.submit_time)}>FB {entry.attacker}</small>
}

function MatrixRegion({
  scoreboard,
  firstBlood,
  onOpenInspector,
  selection,
}: {
  scoreboard: ResourceState<Scoreboard>
  firstBlood: ResourceState<FirstBlood>
  onOpenInspector: OpenInspector
  selection: WarRoomSelection
}) {
  const data = scoreboard.data
  const serviceAnchorTeamId = data?.teams.find((team) => team.highlighted)?.team_id
    ?? data?.teams[0]?.team_id

  return (
    <Region kicker="matrix" resource={scoreboard} title="Team × service matrix">
      <ResourceMessage resource={scoreboard} waiting="Waiting for service matrix" error="Service matrix unavailable" />
      {data !== null && data.tasks.length === 0 && (
        <div className="region-empty"><strong>No services configured</strong><span>The matrix needs at least one task.</span></div>
      )}
      {data !== null && data.tasks.length > 0 && (
        <>
          <div className={`matrix-source-state matrix-source-state--${resourceState(firstBlood)}`}>
            First blood · {resourceState(firstBlood) === 'ready' ? 'SYNC' : resourceState(firstBlood).toUpperCase()}
            {firstBlood.error !== null && firstBlood.data !== null && ` · ${formatLocalTime(firstBlood.lastUpdated)}`}
          </div>
          <div className="matrix-scroll" tabIndex={0} aria-label="Scrollable team service matrix">
            <table className="service-matrix">
              <thead>
                <tr>
                  <th scope="col">Team</th>
                   {data.tasks.map((task) => (
                     <th key={task.id} scope="col">
                       <button
                         aria-expanded={selection?.kind === 'service' && selection.taskId === task.id}
                         aria-haspopup="dialog"
                         aria-label={`Inspect service ${task.name} across all teams`}
                         className="matrix-header-button"
                         disabled={serviceAnchorTeamId === undefined}
                         id={`war-matrix-task-${task.id}`}
                         onClick={() => {
                           if (serviceAnchorTeamId === undefined) return
                           onOpenInspector(
                             { kind: 'service', teamId: serviceAnchorTeamId, taskId: task.id },
                             `war-matrix-task-${task.id}`,
                           )
                         }}
                         type="button"
                       >
                         <strong>{task.name}</strong>
                         <span>{task.ports}</span>
                         <FirstBloodLabel firstBlood={firstBlood.data} taskId={task.id} />
                       </button>
                     </th>
                   ))}
                </tr>
              </thead>
              <tbody>
                {data.teams.map((team) => (
                  <tr key={team.team_id}>
                    <th scope="row">
                      <button
                        aria-expanded={selection?.kind === 'team' && selection.teamId === team.team_id}
                        aria-haspopup="dialog"
                        aria-label={`Inspect team ${team.team}`}
                        className="matrix-header-button"
                        id={`war-matrix-team-${team.team_id}`}
                        onClick={() => onOpenInspector(
                          { kind: 'team', teamId: team.team_id },
                          `war-matrix-team-${team.team_id}`,
                        )}
                        type="button"
                      >
                        <span>#{formatNumber(team.pos).padStart(2, '0')}</span>
                        <strong>{team.team}</strong>
                      </button>
                    </th>
                    {data.tasks.map((task) => {
                      const service = team.services[`${task.id}`]
                      const status = normalizeStatus(service?.status)
                      const cellKey = `${team.team_id}:${task.id}`
                      const detail = service === undefined
                        ? `${team.team}, ${task.name}: status N/A`
                        : `${team.team}, ${task.name}: status ${status}, score ${formatNumber(service.score)}, SLA ${formatNumber(service.sla)}%, stolen ${formatNumber(service.stolen)}, lost ${formatNumber(service.lost)}`
                      return (
                        <td key={task.id}>
                         <button
                            aria-expanded={selection?.kind === 'service' && selection.teamId === team.team_id && selection.taskId === task.id}
                            aria-haspopup="dialog"
                            aria-label={detail}
                            className={`matrix-cell matrix-cell--${statusClass(status)}`}
                            id={`war-matrix-service-${cellKey.replace(':', '-')}`}
                            onClick={() => onOpenInspector(
                              { kind: 'service', teamId: team.team_id, taskId: task.id },
                              `war-matrix-service-${cellKey.replace(':', '-')}`,
                            )}
                            title={detail}
                            type="button"
                          >
                            <strong>{status}</strong>
                            <span>{formatCompactNumber(service?.score)} · {formatNumber(service?.sla)}%</span>
                            <small>+{formatNumber(service?.stolen)} / −{formatNumber(service?.lost)}</small>
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Region>
  )
}

function AttackRows({ attacks, freshKeys }: { attacks: Attack[]; freshKeys: ReadonlySet<string> }) {
  return (
    <ol className="attack-list">
      {attacks.map((attack) => {
        const key = attackIdentityKey(attack)
        return (
          <li key={key}>
            <time dateTime={attack.submit_time}>{formatLocalTime(attack.submit_time)}</time>
            <span className="attack-route"><strong>{attack.attacker}</strong><span aria-hidden="true">→</span><strong>{attack.victim}</strong></span>
            <span className="attack-service">{attack.service}</span>
            <span>R{formatNumber(attack.flag_round)}</span>
            {freshKeys.has(key) && <span className="attack-new">BARU</span>}
          </li>
        )
      })}
    </ol>
  )
}

function AttackFeedRegion({
  resource,
  teams,
}: {
  resource: ResourceState<Attack[]>
  teams: ScoreboardTeam[]
}) {
  const [mode, setMode] = useState<FeedMode>('attacks')
  const [freshKeys, setFreshKeys] = useState<ReadonlySet<string>>(new Set())
  const tracker = useRef<AttackFreshnessTracker>({ initialized: false, seen: new Map() })
  const defenseTeam = getDefenseTeam(teams)
  const visibleAttacks = resource.data === null
    ? []
    : filterAttackFeed(resource.data, mode, defenseTeam)

  useEffect(() => {
    if (resource.data === null) return
    const update = updateAttackFreshness(resource.data, tracker.current, Date.now())
    tracker.current = update.tracker
    setFreshKeys(update.freshKeys)
    if (update.freshKeys.size === 0) return
    const timer = window.setTimeout(() => setFreshKeys(new Set()), ATTACK_FRESHNESS_MS)
    return () => window.clearTimeout(timer)
  }, [resource.data])

  return (
    <Region kicker="activity" resource={resource} title="Attack activity">
      <Tabs.Root
        className="feed-tabs"
        onValueChange={(value) => {
          if (value === 'attacks' || value === 'defense') setMode(value)
        }}
        value={mode}
      >
        <Tabs.List aria-label="Attack activity mode" className="feed-tabs__list">
          <Tabs.Tab value="attacks">ATTACKS</Tabs.Tab>
          <Tabs.Tab value="defense">DEFENSE</Tabs.Tab>
          <Tabs.Indicator className="feed-tabs__indicator" />
        </Tabs.List>
        <Tabs.Panel value="attacks">
          <ResourceMessage resource={resource} waiting="Waiting for attack activity" error="Attack feed unavailable" />
          {resource.data !== null && visibleAttacks.length === 0 && <div className="region-empty"><strong>No attack activity</strong><span>No successful steals are in the current feed.</span></div>}
          {visibleAttacks.length > 0 && <AttackRows attacks={visibleAttacks} freshKeys={freshKeys} />}
        </Tabs.Panel>
        <Tabs.Panel value="defense">
          <ResourceMessage resource={resource} waiting="Waiting for defense activity" error="Defense feed unavailable" />
          {resource.data !== null && visibleAttacks.length === 0 && (
            <div className="region-empty">
              <strong>No defense activity</strong>
              <span>{defenseTeam === null ? 'Waiting for a ranked team.' : `No attacks against ${defenseTeam} are in the current feed.`}</span>
            </div>
          )}
          {visibleAttacks.length > 0 && <AttackRows attacks={visibleAttacks} freshKeys={freshKeys} />}
        </Tabs.Panel>
      </Tabs.Root>
    </Region>
  )
}

function TimelineRegion({ resource }: { resource: ResourceState<TimelinePoint[]> }) {
  const model = useMemo(() => scaleTimelineSeries(
    groupTimelineSeries(resource.data ?? []),
    chartDimensions,
  ), [resource.data])
  const description = model.series.length === 0
    ? 'No score points are available.'
    : `${formatNumber(model.series.length)} team series from round ${formatNumber(model.domain.minRound)} to ${formatNumber(model.domain.maxRound)}.`

  return (
    <Region kicker="timeline" resource={resource} title="Score timeline">
      <ResourceMessage resource={resource} waiting="Waiting for score history" error="Timeline unavailable" />
      {resource.data !== null && resource.data.length === 0 && (
        <div className="region-empty"><strong>No timeline points yet</strong><span>Historical scores will appear after a round is logged.</span></div>
      )}
      {resource.data !== null && resource.data.length > 0 && (
        <>
          <div className="timeline-chart">
            <svg role="img" aria-labelledby="timeline-svg-title timeline-svg-description" viewBox={`0 0 ${chartDimensions.width} ${chartDimensions.height}`}>
              <title id="timeline-svg-title">Team score timeline</title>
              <desc id="timeline-svg-description">{description}</desc>
              {model.yTicks.map((tick) => {
                const y = chartDimensions.height - chartDimensions.inset - (tick - model.domain.minScore) / (model.domain.maxScore - model.domain.minScore) * (chartDimensions.height - chartDimensions.inset * 2)
                return (
                  <g key={tick}>
                    <line className="timeline-grid" x1={chartDimensions.inset} x2={chartDimensions.width - chartDimensions.inset} y1={y} y2={y} />
                    <text className="timeline-label" x={chartDimensions.inset - 8} y={y + 4} textAnchor="end">{formatCompactNumber(tick)}</text>
                  </g>
                )
              })}
              {model.xTicks.map((tick) => {
                const x = chartDimensions.inset + (tick - model.domain.minRound) / (model.domain.maxRound - model.domain.minRound || 1) * (chartDimensions.width - chartDimensions.inset * 2)
                return <text className="timeline-label" key={tick} x={x} y={chartDimensions.height - 16} textAnchor="middle">R{formatNumber(tick)}</text>
              })}
              {model.series.map((series, index) => {
                const path = series.points.map((point, pointIndex) => `${pointIndex === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
                return (
                  <g className={`timeline-series timeline-series--${index % 7}`} key={series.teamId}>
                    <path d={path} vectorEffect="non-scaling-stroke" />
                    {series.points.map((point) => <circle key={`${point.round}:${point.score}`} cx={point.x} cy={point.y} r={4} vectorEffect="non-scaling-stroke" />)}
                  </g>
                )
              })}
            </svg>
          </div>
          <ul aria-label="Timeline legend" className="timeline-legend">
            {model.series.map((series, index) => (
              <li className={`timeline-series--${index % 7}`} key={series.teamId}><span aria-hidden="true" />{series.team}</li>
            ))}
          </ul>
        </>
      )}
    </Region>
  )
}

export function WarRoomWorkspace({
  activeView,
  dashboard,
  onViewChange,
  views,
}: {
  activeView: string
  dashboard: DashboardState
  onViewChange: (viewId: string) => void
  views: readonly WorkspaceView[]
}) {
  const [selection, setSelection] = useState<WarRoomSelection>(null)
  const triggerId = useRef<string | null>(null)
  const openInspector: OpenInspector = (nextSelection, nextTriggerId) => {
    triggerId.current = nextTriggerId
    setSelection(nextSelection)
  }

  return (
    <>
      {dashboard.stale && (
        <div className="stale-banner" role="status">
          RECONNECT · One or more telemetry sources failed. Last-good data remains visible.
        </div>
      )}
      <StatusLegend />
      <Tabs.Root
        className="workspace-tabs war-room-tabs"
        onValueChange={(value) => {
          if (typeof value === 'string') onViewChange(value)
        }}
        value={activeView}
      >
        <Tabs.List aria-label="Workspace views" className="workspace-tabs__list">
          {views.map((view) => <Tabs.Tab className="workspace-tab" key={view.id} value={view.id}>{view.label}</Tabs.Tab>)}
          <Tabs.Indicator className="workspace-tabs__indicator" />
        </Tabs.List>
        <Tabs.Panel className="workspace-tabs__panel" value="overview">
          <div className="overview-grid">
            <ScoreboardRegion
              onOpenInspector={openInspector}
              resource={dashboard.scoreboard}
              selection={selection}
            />
            <AttackFeedRegion resource={dashboard.attacks} teams={dashboard.scoreboard.data?.teams ?? []} />
          </div>
        </Tabs.Panel>
        <Tabs.Panel className="workspace-tabs__panel" value="matrix">
          <MatrixRegion
            firstBlood={dashboard.firstBlood}
            onOpenInspector={openInspector}
            scoreboard={dashboard.scoreboard}
            selection={selection}
          />
        </Tabs.Panel>
        <Tabs.Panel className="workspace-tabs__panel" value="timeline">
          <TimelineRegion resource={dashboard.timeline} />
        </Tabs.Panel>
      </Tabs.Root>
      <WarRoomInspector
        dashboard={dashboard}
        finalFocus={() => triggerId.current === null ? null : document.getElementById(triggerId.current)}
        onClose={() => setSelection(null)}
        selection={selection}
      />
    </>
  )
}
