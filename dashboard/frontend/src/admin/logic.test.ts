import { describe, expect, it } from 'vitest'

import {
  controlOutcomeView,
  formatHistoryRecord,
  orderRecentHistory,
  validatePublicKeyLine,
} from './logic'

describe('admin control presentation', () => {
  it.each([
    ['ok', { label: 'Completed', tone: 'ok' }],
    ['busy', { label: 'Another action in flight', tone: 'busy' }],
    ['failed', { label: 'Failed', tone: 'failed' }],
    ['timeout', { label: 'Timed out', tone: 'timeout' }],
  ] as const)('maps %s outcomes to an operator-facing label and tone', (outcome, expected) => {
    expect(controlOutcomeView(outcome)).toEqual(expected)
  })
})

describe('admin history formatting', () => {
  it('keeps the most recent twenty records in newest-first order', () => {
    const records = Array.from({ length: 21 }, (_, index) => ({
      at: new Date(Date.UTC(2026, 6, 31, 12, index)).toISOString(),
      action: 'start' as const,
      outcome: 'ok' as const,
      exit_code: 0,
      duration_ms: index,
      stderr_tail: '',
    }))

    const ordered = orderRecentHistory(records)

    expect(ordered).toHaveLength(20)
    expect(ordered[0]?.at).toBe(records[20]?.at)
    expect(ordered.at(-1)?.at).toBe(records[1]?.at)
  })

  it('formats time, action, outcome, exit code, and duration for display', () => {
    const at = new Date(2026, 6, 31, 12, 30, 0).toISOString()

    expect(formatHistoryRecord({
      at,
      action: 'pause',
      outcome: 'failed',
      exit_code: 1,
      duration_ms: 1_250,
      stderr_tail: 'ticker refused to stop',
    })).toEqual({
      time: '31 Jul 2026, 12.30.00',
      action: 'PAUSE',
      outcome: { label: 'Failed', tone: 'failed' },
      exitCode: '1',
      duration: '1.250 ms',
    })
  })

  it('uses the existing missing-value marker when no exit code is available', () => {
    expect(formatHistoryRecord({
      at: 'not-a-time',
      action: 'resume',
      outcome: 'timeout',
      exit_code: null,
      duration_ms: 60_000,
      stderr_tail: '',
    })).toMatchObject({ time: '–', exitCode: '–' })
  })
})

describe('public-key line validation', () => {
  it('requires a non-empty value', () => {
    expect(validatePublicKeyLine('   ')).toBe('Paste one public-key line.')
  })

  it.each(['ssh-ed25519 AAAA first\nssh-ed25519 BBBB second', 'ssh-rsa AAAA\rcomment'])(
    'rejects embedded line breaks',
    (value) => {
      expect(validatePublicKeyLine(value)).toBe('Use a single line without line breaks.')
    },
  )

  it('leaves definitive key syntax validation to the server', () => {
    expect(validatePublicKeyLine('ssh-ed25519 AAAAC3Nza test@example')).toBeNull()
    expect(validatePublicKeyLine('not-yet-validated-by-the-client')).toBeNull()
  })
})
