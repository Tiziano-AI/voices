import { expect, test } from '@playwright/test';
import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;

if (!baseUrl) {
  throw new Error('PLAYWRIGHT_BASE_URL is required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

test('closing an in-flight design request prevents late persistence', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Closed Voice');
  await dialog.getByLabel('Voice id').fill('closed_voice');
  await dialog.getByLabel('Voice design').fill('Warm narrator with crisp diction and measured documentary pace.');
  await dialog.getByLabel('Reference text').fill('Every signal matters when the room goes quiet.');
  await dialog.getByRole('button', { name: 'Create voice', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Creating…', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.waitForTimeout(1400);

  const voices = await page.request.get(`${baseUrl}/api/voices`);
  const payload = (await voices.json()) as Array<{ id: string }>;

  expect(payload.map((voice) => voice.id)).not.toContain('closed_voice');
});
