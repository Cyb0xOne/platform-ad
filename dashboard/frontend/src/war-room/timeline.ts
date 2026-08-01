import type { TimelinePoint } from '../data/contracts'

export interface TimelineSeries {
  teamId: number
  team: string
  points: TimelinePoint[]
}

interface TimelineDimensions {
  width: number
  height: number
  inset: number
}

export function groupTimelineSeries(points: TimelinePoint[]): TimelineSeries[] {
  const grouped = new Map<number, TimelineSeries>()

  for (const point of points) {
    const series = grouped.get(point.team_id)
    if (series) {
      series.points.push(point)
    } else {
      grouped.set(point.team_id, { teamId: point.team_id, team: point.team, points: [point] })
    }
  }

  return [...grouped.values()].map((series) => ({
    ...series,
    points: [...series.points].sort((left, right) => left.round - right.round),
  }))
}

function selectTicks(values: number[], limit: number): number[] {
  if (values.length <= limit) return values
  return [...new Set(Array.from({ length: limit }, (_, index) => (
    values[Math.round(index * (values.length - 1) / (limit - 1))]
  )))]
}

export function scaleTimelineSeries(series: TimelineSeries[], dimensions: TimelineDimensions) {
  const points = series.flatMap((entry) => entry.points)
  const rounds = [...new Set(points.map((point) => point.round))].sort((left, right) => left - right)
  const scores = points.map((point) => point.score)
  const minRound = rounds[0] ?? 0
  const maxRound = rounds.at(-1) ?? minRound + 1
  const minScore = Math.min(0, ...scores)
  const rawMaxScore = Math.max(0, ...scores)
  const maxScore = rawMaxScore === minScore ? minScore + 1 : rawMaxScore
  const roundSpan = maxRound - minRound || 1
  const scoreSpan = maxScore - minScore || 1
  const plotWidth = dimensions.width - dimensions.inset * 2
  const plotHeight = dimensions.height - dimensions.inset * 2

  return {
    domain: { minRound, maxRound, minScore, maxScore },
    xTicks: selectTicks(rounds, 7),
    yTicks: Array.from({ length: 5 }, (_, index) => minScore + scoreSpan * index / 4),
    series: series.map((entry) => ({
      ...entry,
      points: entry.points.map((point) => ({
        ...point,
        x: dimensions.inset + (point.round - minRound) / roundSpan * plotWidth,
        y: dimensions.height - dimensions.inset - (point.score - minScore) / scoreSpan * plotHeight,
      })),
    })),
  }
}
