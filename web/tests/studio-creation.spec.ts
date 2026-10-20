import path from 'node:path';
import { expect, test } from '@playwright/test';

import { fakeAudioFilePayload, installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;

if (!baseUrl || !screenshotDir) {
  throw new Error('PLAYWRIGHT_BASE_URL and PLAYWRIGHT_SCREENSHOT_DIR are required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

for (const width of [1440, 390]) {
  test(`design checkbox keeps its label beside the control at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.goto(baseUrl);
    await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
    const checkbox = page.getByRole('dialog').getByLabel('Overwrite existing voice', { exact: true });
    await checkbox.scrollIntoViewIfNeeded();
    const controlBox = await checkbox.boundingBox();
    const text = page.getByRole('dialog').getByText('Overwrite existing voice', { exact: true });
    const textBox = await text.boundingBox();
    expect(controlBox).not.toBeNull();
    expect(textBox).not.toBeNull();
    if (!controlBox || !textBox) throw new Error('Checkbox and label must have visible geometry.');
    expect(controlBox.x + controlBox.width).toBeLessThan(textBox.x);
    expect(Math.abs(controlBox.y + controlBox.height / 2 - textBox.y - textBox.height / 2)).toBeLessThan(2);
    await text.click();
    await expect(checkbox).toBeChecked();
  });
}

test('design flow creates a voice', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Cinematic Guide');
  await dialog.getByLabel('Voice design').fill('Deep, measured, cinematic authority.');
  await dialog.getByLabel('Reference text').fill('Every signal matters when the room goes quiet.');
  await dialog.getByRole('button', { name: 'Create voice', exact: true }).click();
  await expect(page.getByRole('main').getByRole('heading', { name: 'Cinematic Guide', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, 'story-design.png'), fullPage: true });
});

test('prompt-pack batch design creates a voice from the browser surface', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByText('Prompt-pack batch design').click();
  await dialog.getByLabel('Prompt pack').setInputFiles({
    name: 'pack.jsonl',
    mimeType: 'application/jsonl',
    buffer: Buffer.from(
      '{"id":"batch_voice","name":"Batch Voice","instruct":"Warm narrator with crisp diction and measured documentary pace.","text":"Hello from batch."}\n',
      'utf-8',
    ),
  });
  await dialog.getByLabel('Dry run').uncheck();
  await dialog.getByRole('button', { name: 'Run prompt pack', exact: true }).click();
  await expect(dialog.getByText('batch_voice')).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(
    page.getByRole('list', { name: 'Saved voices' }).getByRole('button', { name: 'Select Batch Voice (batch_voice)' }),
  ).toBeVisible();
});

test('closing design flow abandons a late create response', async ({ page }) => {
  await page.goto(baseUrl);
  let releaseDesign: (() => void) | null = null;
  const designReleased = new Promise<void>((resolve) => {
    releaseDesign = resolve;
  });

  await page.route('**/api/design', async (route) => {
    await designReleased;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        summary: {
          id: 'abandoned_voice',
          name: 'Abandoned Voice',
          language: 'English',
          source_kind: 'design',
          description: 'Deep, measured, cinematic authority.',
          created_at: '2026-04-08T12:00:00Z',
        },
        record: {
          schema_version: 2,
          id: 'abandoned_voice',
          name: 'Abandoned Voice',
          created_at: '2026-04-08T12:00:00Z',
          language: 'English',
          base_model_id: 'mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16',
          reference_text: 'Every signal matters when the room goes quiet.',
          reference_sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          source: {
            kind: 'design',
            model_id: 'mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16',
            instruct: 'Deep, measured, cinematic authority.',
          },
        },
        reference_text: 'Every signal matters when the room goes quiet.',
        reference_audio_url: '/api/voices/abandoned_voice/reference-audio',
      }),
    });
  });

  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Abandoned Voice');
  await dialog.getByLabel('Voice design').fill('Deep, measured, cinematic authority.');
  await dialog.getByLabel('Reference text').fill('Every signal matters when the room goes quiet.');
  await dialog.getByRole('button', { name: 'Create voice', exact: true }).click();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  releaseDesign?.();
  await page.waitForTimeout(200);
  await expect(page.getByRole('main').getByRole('heading', { name: 'Abandoned Voice', exact: true })).toHaveCount(0);
});

test('clone from file reviews and saves', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Clone file', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Audio file').setInputFiles(fakeAudioFilePayload('source.wav'));
  await dialog.getByLabel('Name').fill('Imported Voice');
  await dialog.getByRole('button', { name: 'Review transcript', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save clone', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, 'story-clone-review.png'), fullPage: true });
  await dialog.getByRole('button', { name: 'Save clone', exact: true }).click();
  await expect(page.getByRole('main').getByRole('heading', { name: 'Imported Voice', exact: true })).toBeVisible();
});

test('clone retry abandons a late save response', async ({ page }) => {
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
            id: 'discarded_clone',
            name: 'Discarded Clone',
            language: 'English',
            source_kind: 'clone',
            description: 'Imported reference voice',
            created_at: '2026-04-08T12:00:00Z',
          },
          record: {
            schema_version: 2,
            id: 'discarded_clone',
            name: 'Discarded Clone',
            created_at: '2026-04-08T12:00:00Z',
            language: 'English',
            base_model_id: 'mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16',
            reference_text: 'Approved transcript.',
            reference_sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            source: {
              kind: 'clone',
            },
          },
          reference_text: 'Approved transcript.',
          reference_audio_url: '/api/voices/discarded_clone/reference-audio',
        }),
      });
    } catch {
      // The retry path aborts the pending save request before this delayed response resolves.
    }
  });

  await page.getByRole('main').getByRole('button', { name: 'Clone file', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Audio file').setInputFiles(fakeAudioFilePayload('source.wav'));
  await dialog.getByLabel('Name').fill('Discarded Clone');
  await dialog.getByRole('button', { name: 'Review transcript', exact: true }).click();
  await dialog.getByRole('button', { name: 'Save clone', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Saving…', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Review transcript', exact: true })).toBeVisible();

  releaseSave?.();
  await page.waitForTimeout(200);
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('main').getByRole('heading', { name: 'Discarded Clone', exact: true })).toHaveCount(0);
});

test('creation sheet resets review state after close and reopen', async ({ page }) => {
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Clone file', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Audio file').setInputFiles(fakeAudioFilePayload('source.wav'));
  await dialog.getByLabel('Name').fill('Transient Voice');
  await dialog.getByRole('button', { name: 'Review transcript', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save clone', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();

  await page.getByRole('main').getByRole('button', { name: 'Clone file', exact: true }).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('Audio file')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Save clone', exact: true })).toHaveCount(0);
  await expect(dialog.getByLabel('Name')).toHaveValue('');
});

test('details-only delete flow', async ({ page }) => {
  await page.goto(baseUrl);
  const savedVoices = page.getByRole('list', { name: 'Saved voices' });
  await savedVoices.getByRole('button', { name: 'Select Test Voice (radio_spark)' }).click();
  await page.getByRole('button', { name: 'Details', exact: true }).click();
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete voice', exact: true }).click();
  await expect(savedVoices.getByRole('button', { name: 'Select Test Voice (radio_spark)' })).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, 'story-delete.png'), fullPage: true });
});
