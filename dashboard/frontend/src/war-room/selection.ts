import type {
  Attack,
  FirstBlood,
  Scoreboard,
} from '../data/contracts'

export type WarRoomSelection =
  | { kind: 'team'; teamId: number }
  | { kind: 'service'; teamId: number; taskId: number }
  | null

export function resolveTeam(scoreboard: Scoreboard | null, teamId: number) {
  return scoreboard?.teams.find((team) => team.team_id === teamId) ?? null
}

export function resolveServiceContext(
  scoreboard: Scoreboard | null,
  firstBlood: FirstBlood | null,
  teamId: number,
  taskId: number,
) {
  const team = resolveTeam(scoreboard, teamId)
  const task = scoreboard?.tasks.find((entry) => entry.id === taskId) ?? null
  if (team === null || task === null) return null

  return {
    team,
    task,
    service: team.services[`${taskId}`],
    firstBlood: firstBlood?.[`${taskId}`],
  }
}

export function collectTeamAttacks(attacks: Attack[], teamName: string) {
  return {
    made: attacks.filter((attack) => attack.attacker === teamName).slice(0, 8),
    received: attacks.filter((attack) => attack.victim === teamName).slice(0, 8),
  }
}

export function buildSshCommand(ip: string, user = 'team') {
  return `ssh ${user}@${ip}`
}

export function buildIpPorts(ip: string, ports: string) {
  return `${ip}:${ports}`
}
