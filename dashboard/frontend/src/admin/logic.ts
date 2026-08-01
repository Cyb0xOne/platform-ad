import { formatLocalTime, formatNumber } from '../data/formatters'

export type ControlAction = 'start' | 'pause' | 'resume'
export type ControlOutcome = 'ok' | 'busy' | 'failed' | 'timeout'

export interface ControlHistoryRecord {
  at: string
  action: ControlAction
  outcome: ControlOutcome
  exit_code: number | null
  duration_ms: number
  stderr_tail: string
}

const outcomeViews = {
  ok: { label: 'Completed', tone: 'ok' },
  busy: { label: 'Another action in flight', tone: 'busy' },
  failed: { label: 'Failed', tone: 'failed' },
  timeout: { label: 'Timed out', tone: 'timeout' },
} as const satisfies Record<ControlOutcome, { label: string; tone: ControlOutcome }>

export function controlOutcomeView(outcome: ControlOutcome) {
  return outcomeViews[outcome]
}

export function orderRecentHistory(records: readonly ControlHistoryRecord[]): ControlHistoryRecord[] {
  return [...records]
    .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
    .slice(0, 20)
}

export function formatHistoryRecord(record: ControlHistoryRecord) {
  return {
    time: formatLocalTime(record.at),
    action: record.action.toUpperCase(),
    outcome: controlOutcomeView(record.outcome),
    exitCode: formatNumber(record.exit_code),
    duration: `${formatNumber(record.duration_ms)} ms`,
  }
}

export function validatePublicKeyLine(value: string): string | null {
  if (value.trim() === '') return 'Paste one public-key line.'
  if (/\r|\n/.test(value)) return 'Use a single line without line breaks.'
  return null
}
