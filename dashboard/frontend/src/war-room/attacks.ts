import type { Attack, ScoreboardTeam } from '../data/contracts'

export type FeedMode = 'attacks' | 'defense'

export const ATTACK_FRESHNESS_MS = 5_200
const ATTACK_TRACKING_LIMIT = 120

export interface AttackFreshnessTracker {
  initialized: boolean
  seen: ReadonlyMap<string, number>
}

interface FreshnessOptions {
  freshWindowMs?: number
  maxEntries?: number
}

export function attackIdentityKey(attack: Attack): string {
  return JSON.stringify([
    attack.submit_time,
    attack.attacker,
    attack.victim,
    attack.service,
    attack.flag_round,
  ])
}

export function getDefenseTeam(teams: ScoreboardTeam[]): string | null {
  return teams.find((team) => team.highlighted)?.team ?? teams[0]?.team ?? null
}

export function filterAttackFeed(attacks: Attack[], mode: FeedMode, defenseTeam: string | null): Attack[] {
  if (mode === 'attacks') return attacks
  if (defenseTeam === null) return []
  return attacks.filter((attack) => attack.victim === defenseTeam)
}

export function updateAttackFreshness(
  attacks: Attack[],
  tracker: AttackFreshnessTracker,
  now: number,
  options: FreshnessOptions = {},
) {
  const freshWindowMs = options.freshWindowMs ?? ATTACK_FRESHNESS_MS
  const maxEntries = options.maxEntries ?? ATTACK_TRACKING_LIMIT
  const seen = new Map(tracker.seen)
  const currentKeys = attacks.map(attackIdentityKey)

  for (const key of currentKeys) {
    if (!seen.has(key)) seen.set(key, tracker.initialized ? now : now - freshWindowMs)
  }

  const freshKeys = new Set<string>()
  if (tracker.initialized) {
    for (const key of currentKeys) {
      const firstSeen = seen.get(key)
      if (firstSeen !== undefined && now - firstSeen < freshWindowMs) freshKeys.add(key)
    }
  }

  const retained = new Map<string, number>()
  for (const key of currentKeys) retained.set(key, seen.get(key) ?? now)
  const historical = [...seen]
    .filter(([key]) => !retained.has(key))
    .sort((left, right) => right[1] - left[1])

  for (const [key, firstSeen] of historical) {
    if (retained.size >= maxEntries) break
    retained.set(key, firstSeen)
  }

  return {
    tracker: { initialized: true, seen: retained } satisfies AttackFreshnessTracker,
    freshKeys,
  }
}
