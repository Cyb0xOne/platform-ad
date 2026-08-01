import { expect, test } from '@playwright/test'

test('next entry renders its smoke heading', async ({ page }) => {
  await page.goto('/next/')

  await expect(page.getByRole('heading', { name: 'Next dashboard' })).toBeVisible()
})
