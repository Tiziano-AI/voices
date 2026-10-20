import { expect, test } from '@playwright/test';

import { STUDIO_CONNECTION_LOST_MESSAGE } from '../src/lib/api';
import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;

if (!baseUrl) {
  throw new Error('PLAYWRIGHT_BASE_URL is required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

test('audition board generates a large library in bounded batches and keeps moving after failures', async ({
  page,
}) => {
  const requestedVoiceIds: string[] = [];
  const failedVoiceId = 'batch_voice_00';

  await page.route('**/api/preview', async (route) => {
    const payload = route.request().postDataJSON() as { voice_id?: string; text?: string; language?: string | null };
    const voiceId = payload.voice_id ?? 'missing_voice';
    requestedVoiceIds.push(voiceId);

    if (voiceId === failedVoiceId) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error_code: 'GenerationError',
          detail: 'Synthetic first voice failure.',
        }),
      });
      return;
    }

    await route.continue();
  });

  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Batching prevents the board from stampeding the local studio.');

  await expect(page.getByRole('button', { name: 'Generate 8 of 44' })).toBeVisible();
  await page.getByRole('button', { name: 'Generate 8 of 44' }).click();
  await expect(page.locator('.audition-card')).toHaveCount(8);
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(7);
  await expect(page.locator('.audition-card[data-status="error"]')).toHaveCount(1);
  await expect(page.getByRole('status')).toHaveText('7 ready. 0 pending. 1 failed. 36 unattempted.');
  expect(requestedVoiceIds).toHaveLength(8);
  expect(requestedVoiceIds.filter((voiceId) => voiceId === failedVoiceId)).toHaveLength(1);

  await page.getByRole('button', { name: 'Generate next 8' }).click();
  await expect(page.locator('.audition-card')).toHaveCount(16);
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(15);
  await expect(page.locator('.audition-card[data-status="error"]')).toHaveCount(1);
  await expect(page.getByRole('status')).toHaveText('15 ready. 0 pending. 1 failed. 28 unattempted.');
  expect(requestedVoiceIds).toHaveLength(16);
  expect(new Set(requestedVoiceIds).size).toBe(16);
  expect(requestedVoiceIds.filter((voiceId) => voiceId === failedVoiceId)).toHaveLength(1);
});

test('audition board retries connection-loss cards without overlapping the grid', async ({ page }) => {
  let serverAvailable = false;
  let previewRequestCount = 0;

  await page.route('**/api/preview', async (route) => {
    previewRequestCount += 1;
    if (!serverAvailable) {
      await route.abort('failed');
      return;
    }

    await route.continue();
  });

  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('The studio should recover when the local edge comes back.');

  await page.getByRole('button', { name: 'Generate 8 of 44' }).click();
  await expect(page.locator('.audition-card[data-status="error"]')).toHaveCount(8);
  await expect(page.getByText(STUDIO_CONNECTION_LOST_MESSAGE)).toHaveCount(8);
  await expectNoCardOverlap(page);
  await expect(page.getByRole('button', { name: 'Generate next 8' })).toBeEnabled();

  serverAvailable = true;
  for (let index = 0; index < 8; index += 1) {
    await page
      .locator('.audition-card[data-generation="failed"]')
      .first()
      .getByRole('button', { name: 'Retry' })
      .click();
    await expect(page.locator('.audition-card[data-generation="ready"]')).toHaveCount(index + 1);
  }
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(8);
  await expect(page.locator('.audition-card[data-status="error"]')).toHaveCount(0);
  await expectNoCardOverlap(page);
  expect(previewRequestCount).toBe(16);
});

async function expectNoCardOverlap(page: import('@playwright/test').Page): Promise<void> {
  const boxes = await page.locator('.audition-card').evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
        top: rect.top,
      };
    }),
  );

  for (let firstIndex = 0; firstIndex < boxes.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < boxes.length; secondIndex += 1) {
      const first = boxes[firstIndex];
      const second = boxes[secondIndex];
      const overlaps =
        first.left < second.right &&
        first.right > second.left &&
        first.top < second.bottom &&
        first.bottom > second.top;
      expect(overlaps, `cards ${firstIndex} and ${secondIndex} should not overlap`).toBe(false);
    }
  }
}
