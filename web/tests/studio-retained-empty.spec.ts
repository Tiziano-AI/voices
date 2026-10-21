import { expect, type Page, test } from '@playwright/test';

import type { PreviewClip, VoiceSummary } from '../src/lib/types';
import { installStudioBrowserMocks, playedAudioUrls } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
if (!baseUrl) throw new Error('PLAYWRIGHT_BASE_URL is required.');

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

async function exposeSingleVoice(page: Page): Promise<void> {
  const voices = (await (await page.request.get(`${baseUrl}/api/voices`)).json()) as VoiceSummary[];
  const voice = voices.find((item) => item.id === 'noir_narrator');
  if (!voice) throw new Error('The seeded fixture must include noir_narrator.');
  let deleted = false;
  await page.route('**/api/voices', (route) => route.fulfill({ json: deleted ? [] : [voice] }));
  await page.route(`**/api/voices/${voice.id}`, async (route) => {
    if (route.request().method() !== 'DELETE') {
      await route.continue();
      return;
    }
    deleted = true;
    await route.fulfill({ status: 204 });
  });
}

async function removeLastVoice(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Details', exact: true }).click();
  page.once('dialog', (dialog) => void dialog.accept());
  await page.getByRole('button', { name: 'Delete voice', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Choose a saved voice', exact: true })).toBeVisible();
}

for (const exportState of ['pending', 'saved'] as const) {
  test(`removing the last voice retains stage and board clips with a ${exportState} export`, async ({ page }) => {
    await exposeSingleVoice(page);
    const exportPaths: string[] = [];
    const generationPaths: string[] = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.endsWith('/export')) exportPaths.push(path);
      if (['/api/preview', '/api/compare', '/api/render'].includes(path)) generationPaths.push(path);
    });
    await page.goto(baseUrl);
    await page.getByLabel('Line', { exact: true }).fill('Keep the stage performance after deleting its voice.');
    const stageGenerated = page.waitForResponse('**/api/preview');
    await page.getByRole('button', { name: 'Play preview', exact: true }).click();
    const stageClip = (await (await stageGenerated).json()) as PreviewClip;

    const board = page.getByRole('region', { name: 'Audition Board', exact: true });
    await board.getByLabel('Audition text', { exact: true }).fill('Keep the board performance too.');
    const boardGenerated = page.waitForResponse('**/api/preview');
    await board.getByRole('button', { name: 'Generate 1', exact: true }).click();
    const boardClip = (await (await boardGenerated).json()) as PreviewClip;
    const candidate = board.locator('.audition-card');
    await expect(candidate).toHaveAttribute('data-generation', 'ready');

    let releaseExport = () => {};
    const exportGate = new Promise<void>((resolve) => {
      releaseExport = resolve;
    });
    if (exportState === 'pending') {
      await page.route(`**/api/previews/${stageClip.token}/export`, async (route) => {
        await exportGate;
        await route.continue();
      });
    }
    const stageExported = page.waitForResponse(`**/api/previews/${stageClip.token}/export`);
    const stageExportRequested = page.waitForRequest(`**/api/previews/${stageClip.token}/export`);
    await page.getByRole('button', { name: 'Save preview', exact: true }).click();
    await stageExportRequested;
    if (exportState === 'saved') {
      await stageExported;
      await expect(page.getByRole('link', { name: 'Download WAV', exact: true })).toBeVisible();
    }

    await removeLastVoice(page);
    await expect(page.getByRole('heading', { name: 'Start by making a voice.', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Replay preview', exact: true })).toBeEnabled();
    await expect(candidate).toHaveCount(1);
    await expect(candidate).toHaveAttribute('data-current', 'false');
    await expect(candidate.getByRole('button', { name: 'Save original clip', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Play preview', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Compare', exact: true })).toBeDisabled();
    await expect(board.getByRole('button', { name: 'Complete', exact: true })).toBeDisabled();

    if (exportState === 'pending') {
      await expect(page.getByRole('main').getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled();
      releaseExport();
      await stageExported;
    }
    const stageWav = page.getByRole('link', { name: 'Download WAV', exact: true });
    await expect(stageWav).toBeVisible();
    await expect(page.getByRole('main').getByRole('button', { name: 'Save original clip', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Replay preview', exact: true }).click();
    await candidate.getByRole('button', { name: 'Play', exact: true }).click();
    const played = await playedAudioUrls(page);
    expect(played.some((url) => url.endsWith(stageClip.audio_url))).toBe(true);
    expect(played.some((url) => url.endsWith(boardClip.audio_url))).toBe(true);

    await candidate.getByRole('button', { name: 'Save original clip', exact: true }).click();
    const boardWav = candidate.getByRole('link', { name: 'WAV', exact: true });
    await expect(boardWav).toBeVisible();
    expect(await (await page.request.get(`${baseUrl}${await stageWav.getAttribute('href')}`)).body()).toEqual(
      await (await page.request.get(`${baseUrl}${stageClip.audio_url}`)).body(),
    );
    expect(await (await page.request.get(`${baseUrl}${await boardWav.getAttribute('href')}`)).body()).toEqual(
      await (await page.request.get(`${baseUrl}${boardClip.audio_url}`)).body(),
    );
    expect(exportPaths).toEqual([`/api/previews/${stageClip.token}/export`, `/api/previews/${boardClip.token}/export`]);
    expect(generationPaths).toEqual(['/api/preview', '/api/preview']);
  });
}

test('the creation error alert exists before a design failure', async ({ page }) => {
  await page.route('**/api/design', (route) =>
    route.fulfill({ status: 503, json: { error_code: 'GenerationError', detail: 'Synthetic design failure.' } }),
  );
  await page.goto(baseUrl);
  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const alert = dialog.getByRole('alert');
  await expect(alert).toHaveCount(1);
  await expect(alert).toBeEmpty();
  await dialog.getByLabel('Name', { exact: true }).fill('Test Design');
  await dialog.getByLabel('Voice design', { exact: true }).fill('Warm and measured documentary narration.');
  await dialog.getByLabel('Reference text', { exact: true }).fill('A failed attempt should explain what happened.');
  await dialog.getByRole('button', { name: 'Create voice', exact: true }).click();
  await expect(alert).toHaveText('Synthetic design failure.');
});
