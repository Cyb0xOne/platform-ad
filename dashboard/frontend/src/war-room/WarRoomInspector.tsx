import { Dialog } from '@base-ui/react/dialog'
import { Drawer } from '@base-ui/react/drawer'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import type { Attack, ScoreboardTask, ScoreboardTeam } from '../data/contracts'
import { formatLocalTime, formatNumber } from '../data/formatters'
import type { DashboardState } from '../data/polling'
import { ActionButton } from '../shared/shell'
import {
  buildIpPorts,
  buildSshCommand,
  collectTeamAttacks,
  resolveServiceContext,
  resolveTeam,
  type WarRoomSelection,
} from './selection'
import { normalizeStatus, summarizeTeam } from './status'

interface WarRoomInspectorProps {
  dashboard: DashboardState
  finalFocus: () => HTMLElement | null
  onClose: () => void
  selection: WarRoomSelection
}

function useMobileInspector() {
  const [mobile, setMobile] = useState(() => (
    typeof window !== 'undefined' && window.matchMedia('(max-width: 700.1px)').matches
  ))

  useEffect(() => {
    const query = window.matchMedia('(max-width: 700.1px)')
    const update = () => setMobile(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return mobile
}

function fallbackCopy(value: string) {
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.append(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  return copied
}

async function copyText(value: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
      return true
    }
  } catch {
    return fallbackCopy(value)
  }
  return fallbackCopy(value)
}

function CopyAction({ label, value }: { label: string; value: string }) {
  const [feedback, setFeedback] = useState<'copied' | 'failed' | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
  }, [])

  return (
    <ActionButton
      className="inspector-copy-action"
      onClick={() => {
        void copyText(value).then((copied) => {
          setFeedback(copied ? 'copied' : 'failed')
          if (timer.current !== null) window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => setFeedback(null), 1_600)
        })
      }}
      tone="accent"
      type="button"
    >
      <span>{feedback ?? label}</span>
      <code>{value}</code>
    </ActionButton>
  )
}

function InspectorTable({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="inspector-table-wrap">
      <table aria-label={label} className="inspector-table">{children}</table>
    </div>
  )
}

function StatusValue({ value }: { value: string | null | undefined }) {
  const status = normalizeStatus(value)
  return <span className={`inspector-status status-key--${status.toLowerCase().replace('/', '')}`}>{status}</span>
}

function ServiceRows({ tasks, team }: { tasks: ScoreboardTask[]; team: ScoreboardTeam }) {
  return (
    <InspectorTable label={`${team.team} service status`}>
      <thead><tr><th>Service</th><th>Status</th><th>Score</th><th>SLA</th></tr></thead>
      <tbody>
        {tasks.map((task) => {
          const service = team.services[`${task.id}`]
          return (
            <tr key={task.id}>
              <th scope="row">{task.name}</th>
              <td><StatusValue value={service?.status} /></td>
              <td>{formatNumber(service?.score)}</td>
              <td>{formatNumber(service?.sla)}%</td>
            </tr>
          )
        })}
      </tbody>
    </InspectorTable>
  )
}

function AttackRows({ attacks, empty }: { attacks: Attack[]; empty: string }) {
  if (attacks.length === 0) return <p className="inspector-empty">{empty}</p>
  return (
    <ol className="inspector-attacks">
      {attacks.map((attack) => (
        <li key={`${attack.submit_time}:${attack.attacker}:${attack.victim}:${attack.service}:${attack.flag_round}`}>
          <time dateTime={attack.submit_time}>{formatLocalTime(attack.submit_time)}</time>
          <span><strong>{attack.attacker}</strong> → <strong>{attack.victim}</strong></span>
          <span>{attack.service} · R{formatNumber(attack.flag_round)}</span>
        </li>
      ))}
    </ol>
  )
}

function MetricGrid({ team }: { team: ScoreboardTeam }) {
  const summary = summarizeTeam(team)
  return (
    <dl className="inspector-metrics">
      <div><dt>Total</dt><dd>{formatNumber(summary.total)}</dd></div>
      <div><dt>UP</dt><dd>{formatNumber(summary.upCount)} / {formatNumber(summary.serviceCount)}</dd></div>
      <div><dt>Mean SLA</dt><dd>{formatNumber(summary.meanSla)}%</dd></div>
      <div><dt>Stolen</dt><dd>{formatNumber(summary.stolen)}</dd></div>
      <div><dt>Lost</dt><dd>{formatNumber(summary.lost)}</dd></div>
    </dl>
  )
}

function TeamInspector({ dashboard, teamId }: { dashboard: DashboardState; teamId: number }) {
  const scoreboard = dashboard.scoreboard.data
  const team = resolveTeam(scoreboard, teamId)
  if (team === null) {
    return <div className="inspector-body"><p className="inspector-empty" role="status">This team is no longer present in the latest scoreboard poll.</p></div>
  }

  const activity = collectTeamAttacks(dashboard.attacks.data ?? [], team.team)
  return (
    <div className="inspector-body">
      <section className="inspector-section">
        <div className="inspector-heading-line">
          <h3>#{formatNumber(team.pos)} · {team.team}</h3>
          {team.highlighted && <span className="team-card__marker">TIM KITA</span>}
        </div>
        <MetricGrid team={team} />
      </section>
      <section className="inspector-section">
        <h3>Read-only access</h3>
        <div className="inspector-actions">
          <CopyAction label="Copy IP" value={team.ip} />
          <CopyAction label="Copy SSH" value={buildSshCommand(team.ip)} />
        </div>
      </section>
      <section className="inspector-section">
        <h3>Service status</h3>
        <ServiceRows tasks={scoreboard?.tasks ?? []} team={team} />
      </section>
      <section className="inspector-section">
        <h3>Attacks made</h3>
        <AttackRows attacks={activity.made} empty="No attacks made in the current feed." />
      </section>
      <section className="inspector-section">
        <h3>Attacks received</h3>
        <AttackRows attacks={activity.received} empty="No attacks received in the current feed." />
      </section>
    </div>
  )
}

function ServiceInspector({
  dashboard,
  taskId,
  teamId,
}: {
  dashboard: DashboardState
  taskId: number
  teamId: number
}) {
  const scoreboard = dashboard.scoreboard.data
  const context = resolveServiceContext(scoreboard, dashboard.firstBlood.data, teamId, taskId)
  if (context === null) {
    return <div className="inspector-body"><p className="inspector-empty" role="status">This service context is no longer present in the latest scoreboard poll.</p></div>
  }

  const { firstBlood, task, team } = context
  const matchingAttacks = (dashboard.attacks.data ?? [])
    .filter((attack) => attack.service === task.name)
    .slice(0, 8)

  return (
    <div className="inspector-body">
      <section className="inspector-section">
        <h3>{task.name}</h3>
        <dl className="inspector-metadata">
          <div><dt>Ports</dt><dd>{task.ports}</dd></div>
          <div><dt>Checker</dt><dd>{task.checker_type} · {formatNumber(task.checker_timeout)}s</dd></div>
          <div><dt>Operations</dt><dd>{formatNumber(task.puts)} puts · {formatNumber(task.gets)} gets · {formatNumber(task.places)} places</dd></div>
          <div><dt>Get period</dt><dd>{formatNumber(task.get_period)}</dd></div>
          <div><dt>Default score</dt><dd>{formatNumber(task.default_score)}</dd></div>
          <div><dt>First blood</dt><dd>{firstBlood ? `${firstBlood.attacker} · ${formatLocalTime(firstBlood.submit_time)}` : '—'}</dd></div>
        </dl>
      </section>
      <section className="inspector-section">
        <h3>Read-only endpoint · {team.team}</h3>
        <div className="inspector-actions">
          <CopyAction label="Copy IP:ports" value={buildIpPorts(team.ip, task.ports)} />
        </div>
      </section>
      <section className="inspector-section">
        <h3>Per-team status</h3>
        <InspectorTable label={`${task.name} status by team`}>
          <thead><tr><th>Team</th><th>Status</th><th>Score</th><th>SLA</th></tr></thead>
          <tbody>
            {(scoreboard?.teams ?? []).map((entry) => {
              const service = entry.services[`${task.id}`]
              return (
                <tr key={entry.team_id}>
                  <th scope="row">{entry.team}</th>
                  <td><StatusValue value={service?.status} /></td>
                  <td>{formatNumber(service?.score)}</td>
                  <td>{formatNumber(service?.sla)}%</td>
                </tr>
              )
            })}
          </tbody>
        </InspectorTable>
      </section>
      <section className="inspector-section">
        <h3>Matching attacks</h3>
        <AttackRows attacks={matchingAttacks} empty="No matching attacks in the current feed." />
      </section>
    </div>
  )
}

function InspectorContent({ dashboard, selection }: { dashboard: DashboardState; selection: WarRoomSelection }) {
  if (selection === null) return <div className="inspector-body" />
  return selection.kind === 'team'
    ? <TeamInspector dashboard={dashboard} teamId={selection.teamId} />
    : <ServiceInspector dashboard={dashboard} taskId={selection.taskId} teamId={selection.teamId} />
}

function inspectorHeading(dashboard: DashboardState, selection: WarRoomSelection) {
  if (selection === null) return { title: 'War Room inspector', description: 'Read-only public telemetry context.' }
  if (selection.kind === 'team') {
    const team = resolveTeam(dashboard.scoreboard.data, selection.teamId)
    return {
      title: team?.team ?? 'Team unavailable',
      description: 'Team performance, service health, and recent attack activity.',
    }
  }
  const context = resolveServiceContext(
    dashboard.scoreboard.data,
    dashboard.firstBlood.data,
    selection.teamId,
    selection.taskId,
  )
  return {
    title: context?.task.name ?? 'Service unavailable',
    description: 'Task-wide checker context and per-team service status.',
  }
}

export function WarRoomInspector({ dashboard, finalFocus, onClose, selection }: WarRoomInspectorProps) {
  const mobile = useMobileInspector()
  const open = selection !== null
  const heading = inspectorHeading(dashboard, selection)
  const onOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) onClose()
  }

  if (mobile) {
    return (
      <Drawer.Provider>
        <Drawer.Root onOpenChange={onOpenChange} open={open} swipeDirection="down">
          <Drawer.Portal>
            <Drawer.Backdrop className="inspector-backdrop" />
            <Drawer.Viewport className="inspector-viewport inspector-viewport--mobile">
              <Drawer.Popup
                className="inspector-popup inspector-popup--mobile inspector-popup--public"
                finalFocus={finalFocus}
                render={<aside />}
              >
                <Drawer.Content>
                  <div aria-hidden="true" className="drawer-handle" />
                  <header className="inspector-header">
                    <div>
                      <span className="inspector-kicker">Read-only context</span>
                      <Drawer.Title className="inspector-title">{heading.title}</Drawer.Title>
                      <Drawer.Description className="inspector-description">{heading.description}</Drawer.Description>
                    </div>
                    <Drawer.Close render={<ActionButton aria-label="Close inspector">Close</ActionButton>} />
                  </header>
                  <InspectorContent dashboard={dashboard} selection={selection} />
                </Drawer.Content>
              </Drawer.Popup>
            </Drawer.Viewport>
          </Drawer.Portal>
        </Drawer.Root>
      </Drawer.Provider>
    )
  }

  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Portal>
        <Dialog.Backdrop className="inspector-backdrop" />
        <Dialog.Viewport className="inspector-viewport inspector-viewport--desktop">
          <Dialog.Popup
            className="inspector-popup inspector-popup--desktop inspector-popup--public"
            finalFocus={finalFocus}
            render={<aside />}
          >
            <header className="inspector-header">
              <div>
                <span className="inspector-kicker">Read-only context</span>
                <Dialog.Title className="inspector-title">{heading.title}</Dialog.Title>
                <Dialog.Description className="inspector-description">{heading.description}</Dialog.Description>
              </div>
              <Dialog.Close render={<ActionButton aria-label="Close inspector">Close</ActionButton>} />
            </header>
            <InspectorContent dashboard={dashboard} selection={selection} />
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
