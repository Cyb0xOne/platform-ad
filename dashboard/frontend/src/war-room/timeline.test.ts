import { describe, expect, it } from 'vitest'

import type { TimelinePoint } from '../data/contracts'
import { groupTimelineSeries, scaleTimelineSeries } from './timeline'

const points: TimelinePoint[] = [
  { round: 3, team_id: 2, team: 'Ares', score: 60 },
  { round: 2, team_id: 1, team: 'Athena', score: 50 },
  { round: 1, team_id: 2, team: 'Ares', score: 40 },
  { round: 1, team_id: 1, team: 'Athena', score: 20 },
]

describe('timeline series', () => {
  it('preserves team encounter order and sorts rounds within each series', () => {
    const series = groupTimelineSeries(points)

    expect(series.map((entry) => entry.team)).toEqual(['Ares', 'Athena'])
    expect(series[0].points.map((point) => point.round)).toEqual([1, 3])
    expect(series[1].points.map((point) => point.round)).toEqual([1, 2])
  })

  it('includes zero in the score domain and caps x labels at seven', () => {
    const manyRounds = Array.from({ length: 20 }, (_, index) => ({
      round: index + 1,
      team_id: 1,
      team: 'Athena',
      score: index + 10,
    }))
    const scaled = scaleTimelineSeries(groupTimelineSeries(manyRounds), {
      width: 1_000,
      height: 320,
      inset: 40,
    })

    expect(scaled.domain.minScore).toBe(0)
    expect(scaled.xTicks.length).toBeLessThanOrEqual(7)
    expect(scaled.series[0].points.every((point) => (
      point.x >= 40 && point.x <= 960 && point.y >= 40 && point.y <= 280
    ))).toBe(true)
  })

  it('includes zero when every score is negative', () => {
    const scaled = scaleTimelineSeries(groupTimelineSeries([
      { round: 1, team_id: 1, team: 'Athena', score: -10 },
    ]), { width: 100, height: 100, inset: 10 })

    expect(scaled.domain).toMatchObject({ minScore: -10, maxScore: 0 })
  })
})
