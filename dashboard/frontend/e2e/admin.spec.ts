import { expect, test } from '@playwright/test'

test('admin entry renders its smoke heading', async ({ page }) => {
  await page.goto('/admin/')

  await expect(page.getByRole('heading', { name: 'Admin dashboard' })).toBeVisible()
})
