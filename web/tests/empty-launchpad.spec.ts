import path from 'node:path';
import { expect, test } from '@playwright/test';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;

if (!baseUrl || !screenshotDir) {
  throw new Error('PLAYWRIGHT_BASE_URL and PLAYWRIGHT_SCREENSHOT_DIR are required.');
}

test('empty library launchpad', async ({ page }) => {
  await page.goto(baseUrl);
  await expect(page.getByRole('heading', { name: 'Start by making a voice.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Design' })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, 'story-empty-launchpad.png'), fullPage: true });
});
