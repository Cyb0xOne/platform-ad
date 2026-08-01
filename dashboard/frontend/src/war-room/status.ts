import type { ScoreboardTeam } from '../data/contracts'

export type ServiceStatus = 'UP' | 'DOWN' | 'MUMBLE' | 'CORRUPT' | 'ERROR' | 'N/A'

const knownStatuses = new Set<ServiceStatus>(['UP', 'DOWN', 'MUMBLE', 'CORRUPT', 'ERROR'])

export function normalizeStatus(value: string | null | undefined): ServiceStatus {
  const normalized = value?.trim().toUpperCase() as ServiceStatus | undefined
  return normalized !== undefined && knownStatuses.has(normalized) ? normalized : 'N/A'
}

export function summarizeTeam(team: ScoreboardTeam) {
  const services = Object.values(team.services)
  const slaTotal = services.reduce((total, service) => total + service.sla, 0)

  return {
    total: team.total,
    upCount: services.filter((service) => normalizeStatus(service.status) === 'UP').length,
    meanSla: services.length === 0 ? null : slaTotal / services.length,
    serviceCount: services.length,
    stolen: services.reduce((total, service) => total + service.stolen, 0),
    lost: services.reduce((total, service) => total + service.lost, 0),
  }
}
