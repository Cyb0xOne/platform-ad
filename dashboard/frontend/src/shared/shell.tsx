import { Button } from '@base-ui/react/button'
import { Dialog } from '@base-ui/react/dialog'
import { Drawer } from '@base-ui/react/drawer'
import { Tabs } from '@base-ui/react/tabs'
import { Tooltip } from '@base-ui/react/tooltip'
import { useState, type ReactNode } from 'react'

type ShellMode = 'public' | 'admin'
type IconName = 'overview' | 'matrix' | 'pulse' | 'shield' | 'controls' | 'audit' | 'inspect' | 'close'

export interface RailItem {
  icon: IconName
  label: string
  viewId: string
}

export interface WorkspaceView {
  id: string
  label: string
  title: string
  description: string
  regions: readonly string[]
}

interface OperationsShellProps {
  mode: ShellMode
  appName: string
  pageHeading: string
  eyebrow: string
  title: string
  description: string
  networkLabel: string
  navItems: readonly RailItem[]
  defaultView: string
  views: readonly WorkspaceView[]
  activeView?: string
  footer?: ReactNode
  headerStatus?: ReactNode
  inspector?: ReactNode
  onViewChange?: (viewId: string) => void
  workspace?: ReactNode
}

type ActionButtonProps = Omit<Button.Props, 'className'> & {
  className?: string
  tone?: 'neutral' | 'accent'
}

function Icon({ name }: { name: IconName }) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeLinecap: 'square' as const,
    strokeLinejoin: 'miter' as const,
    strokeWidth: 1.6,
  }

  return (
    <svg aria-hidden="true" className="ui-icon" viewBox="0 0 24 24">
      {name === 'overview' && <path {...common} d="M4 5h6v6H4zM14 5h6v3h-6zM14 12h6v7h-6zM4 15h6v4H4z" />}
      {name === 'matrix' && <path {...common} d="M4 4h16v16H4zM4 9h16M4 15h16M9 4v16M15 4v16" />}
      {name === 'pulse' && <path {...common} d="M3 12h4l2-6 4 12 2-6h6" />}
      {name === 'shield' && <path {...common} d="M12 3 19 6v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6zM9 12l2 2 4-5" />}
      {name === 'controls' && <path {...common} d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M7 14v6" />}
      {name === 'audit' && <path {...common} d="M6 3h9l3 3v15H6zM14 3v4h4M9 11h6M9 15h6" />}
      {name === 'inspect' && <path {...common} d="M4 5h16v12H9l-5 4zM8 9h8M8 13h5" />}
      {name === 'close' && <path {...common} d="m6 6 12 12M18 6 6 18" />}
    </svg>
  )
}

export function ActionButton({ className = '', tone = 'neutral', ...props }: ActionButtonProps) {
  return <Button {...props} className={`ui-button ui-button--${tone} ${className}`.trim()} />
}

function RailLink({ active, item, onSelect }: { active: boolean; item: RailItem; onSelect: (viewId: string) => void }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <Button
            aria-current={active ? 'page' : undefined}
            aria-label={item.label}
            className="rail-link"
            onClick={() => onSelect(item.viewId)}
            type="button"
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </Button>
        }
      />
      <Tooltip.Portal>
        <Tooltip.Positioner side="right" sideOffset={10}>
          <Tooltip.Popup className="ui-tooltip">
            <Tooltip.Viewport>{item.label}</Tooltip.Viewport>
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

function InspectorContent({ mode }: { mode: ShellMode }) {
  return (
    <div className="inspector-body">
      <section aria-labelledby={`${mode}-selection-title`} className="inspector-section">
        <h3 id={`${mode}-selection-title`}>Selection</h3>
        <p>No workspace object is selected.</p>
      </section>
      <dl className="inspector-metadata">
        <div>
          <dt>Scope</dt>
          <dd>{mode === 'admin' ? 'Controlled network' : 'Public telemetry'}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>Not connected</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd className="status-text status-text--na">N/A</dd>
        </div>
      </dl>
      <p className="inspector-note">
        Context and actions will appear here when a workspace region provides a selection.
      </p>
    </div>
  )
}

function Inspector({ mode }: { mode: ShellMode }) {
  const title = mode === 'admin' ? 'Admin inspector' : 'War Room inspector'
  const description = mode === 'admin'
    ? 'Context for controlled network administration.'
    : 'Context for the selected public telemetry region.'

  return (
    <>
      <div className="inspector-trigger inspector-trigger--desktop">
        <Dialog.Root>
          <Dialog.Trigger
            render={
              <ActionButton aria-label={`Open ${title}`} tone="accent">
                <Icon name="inspect" />
                <span>Inspect</span>
              </ActionButton>
            }
          />
          <Dialog.Portal>
            <Dialog.Backdrop className="inspector-backdrop" />
            <Dialog.Viewport className="inspector-viewport inspector-viewport--desktop">
              <Dialog.Popup className={`inspector-popup inspector-popup--desktop inspector-popup--${mode}`} render={<aside />}>
                <header className="inspector-header">
                  <div>
                    <span className="inspector-kicker">Context surface</span>
                    <Dialog.Title className="inspector-title">{title}</Dialog.Title>
                    <Dialog.Description className="inspector-description">{description}</Dialog.Description>
                  </div>
                  <Dialog.Close
                    render={
                      <ActionButton aria-label={`Close ${title}`} className="ui-button--icon">
                        <Icon name="close" />
                      </ActionButton>
                    }
                  />
                </header>
                <InspectorContent mode={mode} />
              </Dialog.Popup>
            </Dialog.Viewport>
          </Dialog.Portal>
        </Dialog.Root>
      </div>

      <div className="inspector-trigger inspector-trigger--mobile">
        <Drawer.Provider>
          <Drawer.Root swipeDirection="down">
            <Drawer.Trigger
              render={
                <ActionButton aria-label={`Open ${title}`} tone="accent">
                  <Icon name="inspect" />
                  <span>Inspect</span>
                </ActionButton>
              }
            />
            <Drawer.Portal>
              <Drawer.Backdrop className="inspector-backdrop" />
              <Drawer.Viewport className="inspector-viewport inspector-viewport--mobile">
                <Drawer.Popup className={`inspector-popup inspector-popup--mobile inspector-popup--${mode}`} render={<aside />}>
                  <Drawer.Content>
                    <div aria-hidden="true" className="drawer-handle" />
                    <header className="inspector-header">
                      <div>
                        <span className="inspector-kicker">Context surface</span>
                        <Drawer.Title className="inspector-title">{title}</Drawer.Title>
                        <Drawer.Description className="inspector-description">{description}</Drawer.Description>
                      </div>
                      <Drawer.Close
                        render={
                          <ActionButton aria-label={`Close ${title}`} className="ui-button--icon">
                            <Icon name="close" />
                          </ActionButton>
                        }
                      />
                    </header>
                    <InspectorContent mode={mode} />
                  </Drawer.Content>
                </Drawer.Popup>
              </Drawer.Viewport>
            </Drawer.Portal>
          </Drawer.Root>
        </Drawer.Provider>
      </div>
    </>
  )
}

export function StatusLegend() {
  const statuses = ['UP', 'DOWN', 'MUMBLE', 'CORRUPT', 'ERROR', 'N/A'] as const

  return (
    <section aria-label="Service status token reference" className="status-legend">
      <span className="status-legend__label">Status map</span>
      {statuses.map((status) => (
        <span className={`status-key status-key--${status.toLowerCase().replace('/', '')}`} key={status}>
          <span aria-hidden="true" className="status-key__mark" />
          {status}
        </span>
      ))}
    </section>
  )
}

function WorkspaceTabs({ activeView, onViewChange, views }: { activeView: string; onViewChange: (viewId: string) => void; views: readonly WorkspaceView[] }) {
  return (
    <Tabs.Root
      className="workspace-tabs"
      onValueChange={(value) => {
        if (typeof value === 'string') onViewChange(value)
      }}
      value={activeView}
    >
      <Tabs.List aria-label="Workspace views" className="workspace-tabs__list">
        {views.map((view) => (
          <Tabs.Tab className="workspace-tab" key={view.id} value={view.id}>
            {view.label}
          </Tabs.Tab>
        ))}
        <Tabs.Indicator className="workspace-tabs__indicator" />
      </Tabs.List>

      {views.map((view) => (
        <Tabs.Panel className="workspace-tabs__panel" key={view.id} value={view.id}>
          <section aria-labelledby={`${view.id}-title`} className="workspace-frame" id={view.id}>
            <header className="workspace-frame__header">
              <div>
                <span className="workspace-frame__kicker">Reserved workspace</span>
                <h2 id={`${view.id}-title`}>{view.title}</h2>
              </div>
              <span className="workspace-frame__state">Awaiting source</span>
            </header>
            <div className="workspace-frame__body">
              <p>{view.description}</p>
              <div aria-label="Reserved data regions" className="reserved-regions">
                {view.regions.map((region, index) => (
                  <div className="reserved-region" key={region}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{region}</strong>
                    <small>Not connected</small>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </Tabs.Panel>
      ))}
    </Tabs.Root>
  )
}

export function Readout({ label, value, status }: { label: string; value: string; status?: 'na' | 'up' | 'error' }) {
  return (
    <div className="header-readout">
      <span>{label}</span>
      <strong className={status ? `status-text status-text--${status}` : undefined}>{value}</strong>
    </div>
  )
}

export function OperationsShell({
  mode,
  appName,
  pageHeading,
  eyebrow,
  title,
  description,
  networkLabel,
  navItems,
  defaultView,
  views,
  activeView,
  footer,
  headerStatus,
  inspector,
  onViewChange,
  workspace,
}: OperationsShellProps) {
  const [internalActiveView, setInternalActiveView] = useState(defaultView)
  const currentView = activeView ?? internalActiveView
  const setActiveView = onViewChange ?? setInternalActiveView

  return (
    <Tooltip.Provider closeDelay={0} delay={450} timeout={300}>
      <div className={`ops-shell ops-shell--${mode}`}>
        <a className="skip-link" href="#workspace">Skip to workspace</a>

        <aside aria-label={`${appName} navigation`} className="ops-rail">
          <a aria-label={`${appName} home`} className="rail-mark" href="#workspace">
            <span>{mode === 'admin' ? 'AC' : 'WR'}</span>
          </a>
          <nav aria-label="Primary">
            <ul className="rail-nav">
              {navItems.map((item) => (
                <li key={item.label}>
                  <RailLink active={currentView === item.viewId} item={item} onSelect={setActiveView} />
                </li>
              ))}
            </ul>
          </nav>
          <span className="rail-mode">{mode === 'admin' ? 'ADMIN' : 'PUBLIC'}</span>
        </aside>

        <div className="ops-stage">
          <header className="ops-header">
            <div className="header-identity">
              <span className="header-eyebrow">{eyebrow}</span>
              <h1>{pageHeading}</h1>
              <span className="header-title">{title}</span>
              <p>{description}</p>
            </div>

            {headerStatus ?? (
              <div aria-label="Application status" className="header-status">
                <Readout label="Game" status="na" value="N/A" />
                <Readout label="Round" value="---" />
                <Readout label="Channel" status="up" value="Shell ready" />
                <span className="network-label">{networkLabel}</span>
              </div>
            )}

            {inspector === undefined ? <Inspector mode={mode} /> : inspector}
          </header>

          <main className="ops-workspace" id="workspace" tabIndex={-1}>
            {workspace ?? (
              <>
                <StatusLegend />
                <WorkspaceTabs activeView={currentView} onViewChange={setActiveView} views={views} />
              </>
            )}
          </main>

          <footer className="ops-footer">
            {footer ?? (
              <>
                <span>{appName}</span>
                <span>Foundation shell</span>
                <span>No data source connected</span>
              </>
            )}
          </footer>
        </div>
      </div>
    </Tooltip.Provider>
  )
}
