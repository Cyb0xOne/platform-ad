import { describe, expect, it } from 'vitest'

import type { Attack, ScoreboardTeam } from '../data/contracts'
import {
  attackIdentityKey,
  filterAttackFeed,
  getDefenseTeam,
  updateAttackFreshness,
} from './attacks'

const attacks: Attack[] = [{
  submit_time: '2026-07-31T12:32:00+00:00',
  attacker: 'Ares',
  victim: 'Athena',
  service: 'example',
  flag_round: 12,
}, {
  submit_time: '2026-07-31T12:31:00+00:00',
  attacker: 'Athena',
  victim: 'Ares',
  service: 'example',
  flag_round: 11,
}]

const teams = [
  { team: 'Ares', highlighted: false },
  { team: 'Athena', highlighted: true },
] as ScoreboardTeam[]

describe('attack feed logic', () => {
  it('filters defense activity to the highlighted team with ranked fallback', () => {
    expect(getDefenseTeam(teams)).toBe('Athena')
    expect(getDefenseTeam(teams.map((team) => ({ ...team, highlighted: false })))).toBe('Ares')
    expect(getDefenseTeam([])).toBeNull()
    expect(filterAttackFeed(attacks, 'defense', 'Athena')).toEqual([attacks[0]])
    expect(filterAttackFeed(attacks, 'attacks', 'Athena')).toEqual(attacks)
  })

  it('keys identity on the complete attack tuple', () => {
    expect(attackIdentityKey(attacks[0])).not.toBe(attackIdentityKey(attacks[1]))
    expect(attackIdentityKey(attacks[0])).not.toBe(attackIdentityKey({
      ...attacks[0],
      flag_round: 13,
    }))
  })

  it('never marks the first successful poll new and expires later markers', () => {
    const initial = updateAttackFreshness(attacks, {
      initialized: false,
      seen: new Map(),
    }, 1_000)
    expect(initial.freshKeys.size).toBe(0)

    const nextAttack = { ...attacks[0], submit_time: '2026-07-31T12:33:00+00:00' }
    const next = updateAttackFreshness([nextAttack, ...attacks], initial.tracker, 2_000)
    expect(next.freshKeys).toEqual(new Set([attackIdentityKey(nextAttack)]))

    const expired = updateAttackFreshness([nextAttack, ...attacks], next.tracker, 7_201)
    expect(expired.freshKeys.size).toBe(0)
  })

  it('keeps the tracking map bounded while retaining current rows', () => {
    const tracker = {
      initialized: true,
      seen: new Map([['old-a', 1], ['old-b', 2], ['old-c', 3]]),
    }
    const bounded = updateAttackFreshness(attacks, tracker, 10, { maxEntries: 2 })

    expect(bounded.tracker.seen.size).toBe(2)
    expect([...bounded.tracker.seen.keys()]).toEqual(attacks.map(attackIdentityKey))
  })
})
