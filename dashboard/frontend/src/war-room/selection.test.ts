import { describe, expect, it } from 'vitest'

import type { Attack, FirstBlood, Scoreboard } from '../data/contracts'
import {
  buildIpPorts,
  buildSshCommand,
  collectTeamAttacks,
  resolveServiceContext,
  resolveTeam,
} from './selection'

const scoreboard: Scoreboard = {
  tasks: [{
    id: 11,
    name: 'ledger',
    checker_type: 'stateful',
    checker_timeout: 7,
    puts: 2,
    gets: 3,
    places: 1,
    get_period: 5,
    default_score: 2_500,
    ports: '8080,8443',
  }],
  teams: [{
    team_id: 7,
    team: 'Athena',
    highlighted: true,
    ip: '10.13.37.11',
    total: 120,
    pos: 1,
    services: {
      '11': { status: 'UP', score: 100, stolen: 2, lost: 1, sla: 99.5 },
    },
  }],
}

const firstBlood: FirstBlood = {
  '11': { attacker: 'Ares', submit_time: '2026-07-31T12:20:00+00:00' },
}

const attacks: Attack[] = Array.from({ length: 12 }, (_, index) => ({
  submit_time: `2026-07-31T12:${String(59 - index).padStart(2, '0')}:00+00:00`,
  attacker: index % 2 === 0 ? 'Athena' : 'Ares',
  victim: index % 2 === 0 ? 'Ares' : 'Athena',
  service: 'ledger',
  flag_round: 20 - index,
}))

describe('War Room inspector selection', () => {
  it('resolves teams by team_id and returns null when a team disappears', () => {
    expect(resolveTeam(scoreboard, 7)).toBe(scoreboard.teams[0])
    expect(resolveTeam(scoreboard, 99)).toBeNull()
  })

  it('resolves the selected team, task, service score, and first blood entry', () => {
    expect(resolveServiceContext(scoreboard, firstBlood, 7, 11)).toEqual({
      team: scoreboard.teams[0],
      task: scoreboard.tasks[0],
      service: scoreboard.teams[0].services['11'],
      firstBlood: firstBlood['11'],
    })
    expect(resolveServiceContext(scoreboard, firstBlood, 99, 11)).toBeNull()
    expect(resolveServiceContext(scoreboard, firstBlood, 7, 99)).toBeNull()
  })

  it('keeps feed order while capping attacks made and received at eight each', () => {
    const activity = collectTeamAttacks([...attacks, ...attacks], 'Athena')

    expect(activity.made).toEqual([...attacks, ...attacks].filter((attack) => attack.attacker === 'Athena').slice(0, 8))
    expect(activity.received).toEqual([...attacks, ...attacks].filter((attack) => attack.victim === 'Athena').slice(0, 8))
  })

  it('builds display-only SSH and IP:ports strings', () => {
    expect(buildSshCommand('10.13.37.11')).toBe('ssh team@10.13.37.11')
    expect(buildSshCommand('10.13.37.11', 'operator')).toBe('ssh operator@10.13.37.11')
    expect(buildIpPorts('10.13.37.11', '8080,8443')).toBe('10.13.37.11:8080,8443')
  })
})
