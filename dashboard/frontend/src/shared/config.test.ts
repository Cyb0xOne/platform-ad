import { describe, expect, it } from 'vitest'

import { ADMIN_PATH, NEXT_PATH, POLL_INTERVAL_MS } from './config'

describe('frontend configuration', () => {
  it('defines the public entry paths and polling interval', () => {
    expect(NEXT_PATH).toBe('/next/')
    expect(ADMIN_PATH).toBe('/admin/')
    expect(POLL_INTERVAL_MS).toBe(5_000)
  })
})
