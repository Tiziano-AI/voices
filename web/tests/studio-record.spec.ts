import path from 'node:path';
import { expect, test } from '@playwright/test';
import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;

if (!baseUrl || !screenshotDir) {
  throw new Error('PLAYWRIGHT_BASE_URL and PLAYWRIGHT_SCREENSHOT_DIR are required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

test('browser live-record review and save', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Record live', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Live Studio Voice');
  await dialog.getByLabel('Capture mode').selectOption('free');
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save recording', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, 'story-record-review.png'), fullPage: true });
  await dialog.getByRole('button', { name: 'Save recording', exact: true }).click();
  await expect(page.getByRole('main').getByRole('heading', { name: 'Live Studio Voice', exact: true })).toBeVisible();
});

test('record retry abandons a late save response', async ({ page }) => {
  await page.goto(baseUrl);
  let releaseSave: (() => void) | null = null;
  const saveReleased = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });

  await page.route('**/api/clone/save', async (route) => {
    await saveReleased;
    try {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            id: 'discarded_record',
            name: 'Discarded Record',
            language: 'English',
            source_kind: 'clone',
            description: 'Imported reference voice',
            created_at: '2026-04-08T12:00:00Z',
          },
          record: {
            schema_version: 2,
            id: 'discarded_record',
            name: 'Discarded Record',
            created_at: '2026-04-08T12:00:00Z',
            language: 'English',
            base_model_id: 'mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16',
            reference_text: 'Approved transcript.',
            reference_sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            source: { kind: 'clone' },
          },
          reference_text: 'Approved transcript.',
          reference_audio_url: '/api/voices/discarded_record/reference-audio',
        }),
      });
    } catch {
      // The retry path aborts the pending save request before this delayed response resolves.
    }
  });

  await page.getByRole('main').getByRole('button', { name: 'Record live', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Discarded Record');
  await dialog.getByLabel('Capture mode').selectOption('free');
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save recording', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Save recording', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Saving…', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Start recording', exact: true })).toBeVisible();

  releaseSave?.();
  await page.waitForTimeout(200);
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('main').getByRole('heading', { name: 'Discarded Record', exact: true })).toHaveCount(0);
});

test('record review does not rerun when metadata changes during processing', async ({ page }) => {
  await page.goto(baseUrl);
  let reviewRequestCount = 0;
  let releaseReview: (() => void) | null = null;
  const reviewReleased = new Promise<void>((resolve) => {
    releaseReview = resolve;
  });

  await page.route('**/api/clone/review', async (route) => {
    reviewRequestCount += 1;
    await reviewReleased;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        review_token: 'late-review',
        suggested_voice_id: 'steady-voice',
        transcript: 'Hello from local STT.',
        language: 'English',
        duration_seconds: 4,
        segments: [],
        audio_url: '/api/assets/late-review.wav',
      }),
    });
  });

  await page.getByRole('main').getByRole('button', { name: 'Record live', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Capture mode').selectOption('free');
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByText('Preparing transcript review…')).toBeVisible();
  await dialog.getByLabel('Name').fill('Retyped Voice');
  await dialog.getByLabel('Voice id').fill('retyped-voice');
  await page.waitForTimeout(200);
  expect(reviewRequestCount).toBe(1);
  releaseReview?.();
  await expect(dialog.getByRole('button', { name: 'Save recording', exact: true })).toBeVisible();
});

test('browser live-record surfaces short free-take rejection', async ({ page }) => {
  await page.route('**/api/clone/review', async (route) => {
    await route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        error_code: 'InvalidInputError',
        detail: 'Recorded take must be at least 3s before transcript review.',
      }),
    });
  });

  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Record live', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Capture mode').selectOption('free');
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByText('Recorded take must be at least 3s before transcript review.').first()).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Save recording', exact: true })).toHaveCount(0);
});
