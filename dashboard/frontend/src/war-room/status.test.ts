import { describe, expect, it } from 'vitest'

import type { ScoreboardTeam } from '../data/contracts'
import { normalizeStatus, summarizeTeam } from './status'

const team: ScoreboardTeam = {
  team_id: 7,
  team: 'Athena',
  highlighted: true,
  ip: '10.13.37.11',
  total: 120,
  pos: 1,
  services: {
    '1': { status: 'up', score: 100, stolen: 2, lost: 1, sla: 99.5 },
    '2': { status: 'DOWN', score: 80, stolen: 1, lost: 3, sla: 50.5 },
    '3': { status: 'unexpected', score: 70, stolen: 0, lost: 0, sla: 75 },
  },
}

describe('service status and team summaries', () => {
  it('normalizes only the known status set', () => {
    expect(normalizeStatus('up')).toBe('UP')
    expect(normalizeStatus('MUMBLE')).toBe('MUMBLE')
    expect(normalizeStatus('CORRUPT')).toBe('CORRUPT')
    expect(normalizeStatus('error')).toBe('ERROR')
    expect(normalizeStatus('unknown')).toBe('N/A')
    expect(normalizeStatus(null)).toBe('N/A')
    expect(normalizeStatus(undefined)).toBe('N/A')
  })

  it('summarizes available services without inventing missing values', () => {
    expect(summarizeTeam(team)).toEqual({
      total: 120,
      upCount: 1,
      meanSla: 75,
      serviceCount: 3,
      stolen: 3,
      lost: 4,
    })
    expect(summarizeTeam({ ...team, services: {} }).meanSla).toBeNull()
  })
})
