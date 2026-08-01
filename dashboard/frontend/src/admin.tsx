import { AlertDialog } from '@base-ui/react/alert-dialog'
import { Tabs } from '@base-ui/react/tabs'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { createRoot } from 'react-dom/client'

import {
  controlOutcomeView,
  formatHistoryRecord,
  orderRecentHistory,
  validatePublicKeyLine,
  type ControlAction,
  type ControlHistoryRecord,
  type ControlOutcome,
} from './admin/logic'
import { ActionButton, OperationsShell, Readout } from './shared/shell'
import './styles.css'
import './admin/admin.css'

const railItems = [
  { icon: 'controls', label: 'Control', viewId: 'control' },
  { icon: 'shield', label: 'Hosts', viewId: 'hosts' },
  { icon: 'audit', label: 'Audit', viewId: 'audit' },
] as const

const workspaceViews = [
  {
    id: 'control',
    label: 'Control',
    title: 'ForcAD lifecycle',
    description: 'Confirmed start, pause, and resume operations.',
    regions: [],
  },
  {
    id: 'hosts',
    label: 'Hosts',
    title: 'Vulnbox SSH keys',
    description: 'Team-scoped authorized-key management.',
    regions: [],
  },
  {
    id: 'audit',
    label: 'Audit',
    title: 'Operation history',
    description: 'The twenty most recent lifecycle operations.',
    regions: [],
  },
] as const

const lifecycleActions: ReadonlyArray<{
  action: ControlAction
  description: string
  effect: string
  label: string
}> = [
  {
    action: 'start',
    label: 'Start ForcAD',
    description: 'Start the game engine in fast mode.',
    effect: 'This runs start --fast, resumes round ticking, and enables flag intake.',
  },
  {
    action: 'pause',
    label: 'Pause ForcAD',
    description: 'Freeze the active game loop.',
    effect: 'This stops the round ticker and flag intake until an admin resumes them.',
  },
  {
    action: 'resume',
    label: 'Resume ForcAD',
    description: 'Restart a paused game loop.',
    effect: 'This restarts the round ticker and flag intake from the paused state.',
  },
]

interface AdminTeam {
  team_id: number
  team: string
  ip: string
}

interface AuthorizedKey {
  type: string
  comment: string
  fingerprint: string | null
}

interface AuthorizedKeys {
  team: string
  ip: string
  user: string
  keys: AuthorizedKey[]
}

interface AddKeyResult {
  team: string
  ip: string
  user: string
  totalKeys: string
}

interface ControlResult {
  action: ControlAction
  detail: string
  outcome: ControlOutcome
}

type RequestState = 'loading' | 'ready' | 'error'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isControlAction(value: unknown): value is ControlAction {
  return value === 'start' || value === 'pause' || value === 'resume'
}

function isControlOutcome(value: unknown): value is ControlOutcome {
  return value === 'ok' || value === 'busy' || value === 'failed' || value === 'timeout'
}

function parseHistory(value: unknown): ControlHistoryRecord[] {
  if (!Array.isArray(value)) throw new Error('History response was not an array.')
  const records = value.filter((entry): entry is ControlHistoryRecord => (
    isRecord(entry)
    && typeof entry.at === 'string'
    && isControlAction(entry.action)
    && isControlOutcome(entry.outcome)
    && (entry.exit_code === null || typeof entry.exit_code === 'number')
    && typeof entry.duration_ms === 'number'
    && typeof entry.stderr_tail === 'string'
  ))
  if (records.length !== value.length) throw new Error('History response contained an invalid record.')
  return orderRecentHistory(records)
}

function parseTeams(value: unknown): AdminTeam[] {
  if (!Array.isArray(value)) throw new Error('Team response was not an array.')
  const teams = value.filter((entry): entry is AdminTeam => (
    isRecord(entry)
    && typeof entry.team_id === 'number'
    && typeof entry.team === 'string'
    && typeof entry.ip === 'string'
  ))
  if (teams.length !== value.length) throw new Error('Team response contained an invalid record.')
  return teams
}

function parseAuthorizedKeys(value: unknown): AuthorizedKeys {
  if (!isRecord(value) || !Array.isArray(value.keys)) {
    throw new Error('Authorized-key response was invalid.')
  }
  const keys = value.keys.filter((entry): entry is AuthorizedKey => (
    isRecord(entry)
    && typeof entry.type === 'string'
    && typeof entry.comment === 'string'
    && (entry.fingerprint === null || typeof entry.fingerprint === 'string')
  ))
  if (
    keys.length !== value.keys.length
    || typeof value.team !== 'string'
    || typeof value.ip !== 'string'
    || typeof value.user !== 'string'
  ) {
    throw new Error('Authorized-key response contained an invalid record.')
  }
  return { team: value.team, ip: value.ip, user: value.user, keys }
}

function parseAddKeyResult(value: unknown): AddKeyResult | null {
  if (
    !isRecord(value)
    || value.ok !== true
    || typeof value.team !== 'string'
    || typeof value.ip !== 'string'
    || typeof value.user !== 'string'
    || (typeof value.total_keys !== 'number' && typeof value.total_keys !== 'string')
  ) return null
  return {
    team: value.team,
    ip: value.ip,
    user: value.user,
    totalKeys: String(value.total_keys),
  }
}

function responseDetail(value: unknown, fallback: string): string {
  if (!isRecord(value)) return fallback
  if (typeof value.detail === 'string' && value.detail.trim() !== '') return value.detail
  if (typeof value.stderr_tail === 'string' && value.stderr_tail.trim() !== '') return value.stderr_tail
  return fallback
}

async function adminRequest(path: string, init: RequestInit = {}) {
  const response = await fetch(`/api/admin${path}`, {
    ...init,
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
  })
  const body: unknown = await response.json().catch(() => null)
  return { response, body }
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
  const [feedback, setFeedback] = useState<'Copied' | 'Copy failed' | null>(null)
  return (
    <ActionButton
      className="admin-copy-action"
      onClick={() => {
        void copyText(value).then((copied) => setFeedback(copied ? 'Copied' : 'Copy failed'))
      }}
      type="button"
    >
      <span>{feedback ?? label}</span>
      <code>{value}</code>
    </ActionButton>
  )
}

function StateMessage({ state, error, empty }: { state: RequestState; error: string | null; empty: string }) {
  if (state === 'loading') {
    return <div className="admin-state admin-state--loading" role="status"><strong>Loading</strong><span>Requesting the admin listener…</span></div>
  }
  if (state === 'error') {
    return <div className="admin-state admin-state--error" role="alert"><strong>Request failed</strong><span>{error}</span></div>
  }
  return <div className="admin-state"><strong>Nothing to show</strong><span>{empty}</span></div>
}

function HistoryPanel({
  error,
  records,
  state,
  title,
}: {
  error: string | null
  records: ControlHistoryRecord[]
  state: RequestState
  title: string
}) {
  return (
    <section aria-labelledby={`${title.replaceAll(' ', '-').toLowerCase()}-title`} className="admin-panel admin-history">
      <header className="admin-panel__header">
        <div>
          <span>Control ledger</span>
          <h2 id={`${title.replaceAll(' ', '-').toLowerCase()}-title`}>{title}</h2>
        </div>
        <span className={`admin-panel__state admin-panel__state--${state}`}>{state}</span>
      </header>
      {records.length === 0 ? (
        <StateMessage error={error} state={state} empty="No lifecycle operations have been recorded." />
      ) : (
        <>
          {state === 'loading' && <p className="admin-inline-state" role="status">Refreshing operation history…</p>}
          {state === 'error' && <p className="admin-inline-state admin-inline-state--error" role="alert">{error}</p>}
          <div className="admin-table-wrap">
            <table className="admin-history-table">
              <thead>
                <tr><th>Time</th><th>Action</th><th>Outcome</th><th>Exit code</th><th>Duration</th></tr>
              </thead>
              <tbody>
                {records.map((record, index) => {
                  const row = formatHistoryRecord(record)
                  return (
                    <tr key={`${record.at}:${record.action}:${index}`}>
                      <td><time dateTime={record.at}>{row.time}</time></td>
                      <td><strong>{row.action}</strong></td>
                      <td><span className={`admin-outcome admin-outcome--${row.outcome.tone}`}>{row.outcome.label}</span></td>
                      <td>{row.exitCode}</td>
                      <td>{row.duration}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

function LifecycleAction({
  action,
  description,
  disabled,
  effect,
  label,
  onConfirm,
}: {
  action: ControlAction
  description: string
  disabled: boolean
  effect: string
  label: string
  onConfirm: (action: ControlAction) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <article className={`admin-control-card admin-control-card--${action}`}>
      <div>
        <span>{action}</span>
        <h3>{label}</h3>
        <p>{description}</p>
      </div>
      <AlertDialog.Root onOpenChange={setOpen} open={open}>
        <AlertDialog.Trigger
          render={
            <ActionButton disabled={disabled} tone="accent" type="button">
              {disabled ? 'Action locked' : label}
            </ActionButton>
          }
        />
        <AlertDialog.Portal>
          <AlertDialog.Backdrop className="admin-dialog-backdrop" />
          <AlertDialog.Viewport className="admin-dialog-viewport">
            <AlertDialog.Popup className="admin-dialog-popup">
              <span className="admin-dialog-kicker">Confirmation required</span>
              <AlertDialog.Title className="admin-dialog-title">Confirm {action}</AlertDialog.Title>
              <AlertDialog.Description className="admin-dialog-description">{effect}</AlertDialog.Description>
              <p className="admin-dialog-warning">This operation changes the live ForcAD lifecycle.</p>
              <div className="admin-dialog-actions">
                <AlertDialog.Close render={<ActionButton type="button">Cancel</ActionButton>} />
                <ActionButton
                  onClick={() => {
                    setOpen(false)
                    onConfirm(action)
                  }}
                  tone="accent"
                  type="button"
                >
                  Confirm {action}
                </ActionButton>
              </div>
            </AlertDialog.Popup>
          </AlertDialog.Viewport>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </article>
  )
}

function AdminDashboard() {
  const [activeView, setActiveView] = useState('control')
  const [history, setHistory] = useState<ControlHistoryRecord[]>([])
  const [historyState, setHistoryState] = useState<RequestState>('loading')
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [inFlight, setInFlight] = useState<ControlAction | null>(null)
  const [controlResult, setControlResult] = useState<ControlResult | null>(null)
  const [teams, setTeams] = useState<AdminTeam[]>([])
  const [teamsState, setTeamsState] = useState<RequestState>('loading')
  const [teamsError, setTeamsError] = useState<string | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null)
  const [authorizedKeys, setAuthorizedKeys] = useState<AuthorizedKeys | null>(null)
  const [keysState, setKeysState] = useState<RequestState>('loading')
  const [keysError, setKeysError] = useState<string | null>(null)
  const [keyInput, setKeyInput] = useState('')
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keySubmitting, setKeySubmitting] = useState(false)
  const [keyResult, setKeyResult] = useState<AddKeyResult | null>(null)
  const keysRequest = useRef(0)

  const loadHistory = useCallback(async () => {
    setHistoryState('loading')
    setHistoryError(null)
    try {
      const { response, body } = await adminRequest('/control/history')
      if (!response.ok) throw new Error(responseDetail(body, 'Could not load operation history.'))
      setHistory(parseHistory(body))
      setHistoryState('ready')
    } catch (reason) {
      setHistoryError(reason instanceof Error ? reason.message : String(reason))
      setHistoryState('error')
    }
  }, [])

  const loadTeams = useCallback(async () => {
    setTeamsState('loading')
    setTeamsError(null)
    try {
      const { response, body } = await adminRequest('/teams')
      if (!response.ok) throw new Error(responseDetail(body, 'Could not load teams.'))
      const nextTeams = parseTeams(body)
      setTeams(nextTeams)
      setSelectedTeamId((current) => current ?? nextTeams[0]?.team_id ?? null)
      setTeamsState('ready')
    } catch (reason) {
      setTeamsError(reason instanceof Error ? reason.message : String(reason))
      setTeamsState('error')
    }
  }, [])

  const loadKeys = useCallback(async () => {
    const requestId = ++keysRequest.current
    if (selectedTeamId === null) {
      setAuthorizedKeys(null)
      setKeysState('ready')
      return
    }
    setAuthorizedKeys(null)
    setKeysState('loading')
    setKeysError(null)
    try {
      const { response, body } = await adminRequest(`/team/${selectedTeamId}/authorized_keys`)
      if (!response.ok) throw new Error(responseDetail(body, 'Could not load authorized keys.'))
      const nextKeys = parseAuthorizedKeys(body)
      if (requestId !== keysRequest.current) return
      setAuthorizedKeys(nextKeys)
      setKeysState('ready')
    } catch (reason) {
      if (requestId !== keysRequest.current) return
      setKeysError(reason instanceof Error ? reason.message : String(reason))
      setKeysState('error')
    }
  }, [selectedTeamId])

  useEffect(() => {
    void loadHistory()
    void loadTeams()
  }, [loadHistory, loadTeams])

  useEffect(() => {
    void loadKeys()
  }, [loadKeys])

  const runControl = async (action: ControlAction) => {
    setInFlight(action)
    setControlResult(null)
    try {
      const { response, body } = await adminRequest(`/control/${action}`, { method: 'POST' })
      const outcome: ControlOutcome = response.ok && isRecord(body) && body.ok === true
        ? 'ok'
        : response.status === 409
          ? 'busy'
          : response.status === 504
            ? 'timeout'
            : 'failed'
      const detail = outcome === 'ok'
        ? `${action.toUpperCase()} completed by the admin listener.`
        : responseDetail(body, `${action.toUpperCase()} did not complete.`)
      setControlResult({ action, detail, outcome })
    } catch (reason) {
      setControlResult({
        action,
        detail: reason instanceof Error ? reason.message : String(reason),
        outcome: 'failed',
      })
    } finally {
      await loadHistory()
      setInFlight(null)
    }
  }

  const submitKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const validation = validatePublicKeyLine(keyInput)
    setKeyError(validation)
    setKeyResult(null)
    if (validation !== null || selectedTeamId === null) return

    setKeySubmitting(true)
    try {
      const { response, body } = await adminRequest(`/team/${selectedTeamId}/authorized_key`, {
        method: 'POST',
        body: JSON.stringify({ key: keyInput.trim() }),
      })
      const result = parseAddKeyResult(body)
      if (!response.ok || result === null) {
        throw new Error(responseDetail(body, 'The admin listener rejected the public key.'))
      }
      setKeyInput('')
      setKeyResult(result)
      await loadKeys()
    } catch (reason) {
      setKeyError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setKeySubmitting(false)
    }
  }

  const selectedTeam = teams.find((team) => team.team_id === selectedTeamId) ?? null
  const controlView = controlResult === null ? null : controlOutcomeView(controlResult.outcome)
  const controlStatus = inFlight !== null
    ? inFlight.toUpperCase()
    : controlResult?.outcome.toUpperCase() ?? 'IDLE'
  const controlStatusTone = controlResult?.outcome === 'ok'
    ? 'up'
    : controlResult?.outcome === 'failed'
      ? 'error'
      : 'na'

  return (
    <OperationsShell
      activeView={activeView}
      appName="A/D Admin Console"
      defaultView="control"
      description="Restricted operator surface for the loopback admin listener"
      eyebrow="Attack-Defense // Network control"
      footer={
        <>
          <span>A/D Admin Console</span>
          <span>Loopback listener · network only</span>
          <span>{history.length} recent operations</span>
        </>
      }
      headerStatus={
        <div aria-label="Admin console status" className="header-status admin-header-status">
          <Readout label="Control" status={controlStatusTone} value={controlStatus} />
          <Readout label="History" status={historyState === 'error' ? 'error' : historyState === 'ready' ? 'up' : 'na'} value={`${history.length} records`} />
          <Readout label="Teams" status={teamsState === 'error' ? 'error' : teamsState === 'ready' ? 'up' : 'na'} value={`${teams.length} loaded`} />
          <span className="network-label">Admin only</span>
        </div>
      }
      inspector={<span className="admin-scope"><span>Surface</span><strong>Loopback</strong></span>}
      mode="admin"
      navItems={railItems}
      networkLabel="Admin only"
      onViewChange={setActiveView}
      pageHeading="Admin dashboard"
      title="Control plane"
      views={workspaceViews}
      workspace={
        <Tabs.Root
          className="workspace-tabs admin-tabs"
          onValueChange={(value) => {
            if (typeof value === 'string') setActiveView(value)
          }}
          value={activeView}
        >
          <Tabs.List aria-label="Admin workspace views" className="workspace-tabs__list">
            {workspaceViews.map((view) => <Tabs.Tab className="workspace-tab" key={view.id} value={view.id}>{view.label}</Tabs.Tab>)}
            <Tabs.Indicator className="workspace-tabs__indicator" />
          </Tabs.List>

          <Tabs.Panel className="workspace-tabs__panel" value="control">
            <div className="admin-control-layout">
              <section aria-labelledby="lifecycle-title" className="admin-panel admin-lifecycle">
                <header className="admin-panel__header">
                  <div><span>ForcAD control</span><h2 id="lifecycle-title">Lifecycle actions</h2></div>
                  <span className={`admin-panel__state ${inFlight === null ? 'admin-panel__state--ready' : 'admin-panel__state--loading'}`}>
                    {inFlight === null ? 'ready' : `${inFlight} running`}
                  </span>
                </header>
                <div className="admin-control-grid">
                  {lifecycleActions.map((item) => (
                    <LifecycleAction
                      {...item}
                      disabled={inFlight !== null}
                      key={item.action}
                      onConfirm={(action) => void runControl(action)}
                    />
                  ))}
                </div>
                {controlResult !== null && controlView !== null && (
                  <div className={`admin-result admin-result--${controlView.tone}`} role="status">
                    <span>{controlResult.action}</span>
                    <strong>{controlView.label}</strong>
                    <p>{controlResult.detail}</p>
                  </div>
                )}
              </section>
              <HistoryPanel error={historyError} records={history} state={historyState} title="Recent operations" />
            </div>
          </Tabs.Panel>

          <Tabs.Panel className="workspace-tabs__panel" value="hosts">
            <section aria-labelledby="ssh-keys-title" className="admin-panel admin-keys">
              <header className="admin-panel__header">
                <div><span>Controlled access</span><h2 id="ssh-keys-title">Vulnbox SSH keys</h2></div>
                <span className={`admin-panel__state admin-panel__state--${teamsState}`}>{teamsState}</span>
              </header>
              {teamsState !== 'ready' || teams.length === 0 ? (
                <StateMessage error={teamsError} state={teamsState} empty="No teams are available to manage." />
              ) : (
                <div className="admin-key-layout">
                  <div className="admin-team-context">
                    <label htmlFor="admin-team-select">Team</label>
                    <select
                      id="admin-team-select"
                      onChange={(event) => {
                        setSelectedTeamId(Number(event.target.value))
                        setKeyError(null)
                        setKeyResult(null)
                      }}
                      value={selectedTeamId ?? ''}
                    >
                      {teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team} · {team.ip}</option>)}
                    </select>
                    {selectedTeam !== null && <p>{selectedTeam.team} · {selectedTeam.ip}</p>}
                    {authorizedKeys !== null && (
                      <div className="admin-copy-grid">
                        <CopyAction label="Copy IP" value={authorizedKeys.ip} />
                        <CopyAction label="Copy SSH" value={`ssh ${authorizedKeys.user}@${authorizedKeys.ip}`} />
                      </div>
                    )}
                  </div>

                  <section aria-labelledby="installed-keys-title" className="admin-key-list-panel">
                    <div className="admin-subheader">
                      <h3 id="installed-keys-title">Installed keys</h3>
                      {authorizedKeys !== null && <span>{authorizedKeys.keys.length}</span>}
                    </div>
                    {keysState !== 'ready' || authorizedKeys === null || authorizedKeys.keys.length === 0 ? (
                      <StateMessage error={keysError} state={keysState} empty="This team has no installed public keys." />
                    ) : (
                      <ul className="admin-key-list">
                        {authorizedKeys.keys.map((key, index) => (
                          <li key={`${key.fingerprint ?? key.type}:${index}`}>
                            <span>{key.type}</span>
                            <strong>{key.comment || 'No comment'}</strong>
                            <code>{key.fingerprint ?? 'Fingerprint unavailable'}</code>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <form className="admin-key-form" onSubmit={submitKey}>
                    <div className="admin-subheader"><h3>Add public key</h3><span>Ctrl / Cmd + Enter</span></div>
                    <label htmlFor="admin-public-key">Public-key line</label>
                    <textarea
                      aria-describedby="admin-public-key-help admin-public-key-error"
                      aria-invalid={keyError === null ? undefined : true}
                      id="admin-public-key"
                      onChange={(event) => {
                        setKeyInput(event.target.value)
                        if (keyError !== null) setKeyError(validatePublicKeyLine(event.target.value))
                      }}
                      onKeyDown={(event: KeyboardEvent<HTMLTextAreaElement>) => {
                        if (
                          event.key === 'Enter'
                          && (event.ctrlKey || event.metaKey)
                          && keyInput.trim() !== ''
                          && !keySubmitting
                        ) {
                          event.preventDefault()
                          event.currentTarget.form?.requestSubmit()
                        }
                      }}
                      placeholder="ssh-ed25519 AAAA… operator@example"
                      rows={4}
                      value={keyInput}
                    />
                    <p id="admin-public-key-help">One non-empty line. The admin listener performs definitive key syntax validation.</p>
                    {keyError !== null && <p className="admin-form-message admin-form-message--error" id="admin-public-key-error" role="alert">{keyError}</p>}
                    {keyResult !== null && (
                      <p className="admin-form-message admin-form-message--ok" role="status">
                        Added for {keyResult.team} · {keyResult.user}@{keyResult.ip} · {keyResult.totalKeys} total keys
                      </p>
                    )}
                    <ActionButton disabled={keyInput.trim() === '' || keySubmitting} tone="accent" type="submit">
                      {keySubmitting ? 'Adding key…' : 'Add key'}
                    </ActionButton>
                  </form>
                </div>
              )}
            </section>
          </Tabs.Panel>

          <Tabs.Panel className="workspace-tabs__panel" value="audit">
            <HistoryPanel error={historyError} records={history} state={historyState} title="Operation history" />
          </Tabs.Panel>
        </Tabs.Root>
      }
    />
  )
}

createRoot(document.getElementById('root')!).render(<AdminDashboard />)
