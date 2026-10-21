import path from 'node:path';
import { expect, test } from '@playwright/test';

import type { CompareResult } from '../src/lib/types';
import { installStudioBrowserMocks, playedAudioUrls } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;
if (!baseUrl || !screenshotDir) throw new Error('The browser fixture environment is required.');

for (const failure of [
  { name: 'generation', code: 'GenerationError', detail: 'Synthetic second-voice failure.' },
  {
    name: 'preview storage',
    code: 'PreviewStorageError',
    detail:
      "Preview audio for voice 'radio_spark' could not be saved. Check disk space and temporary-folder permissions before retrying.",
  },
  {
    name: 'reference read',
    code: 'InvalidVoiceEntryError',
    detail:
      "Voice 'radio_spark' reference could not be read. Check its files, permissions and storage before retrying.",
  },
]) {
  test(`partial compare after ${failure.name} failure preserves exports and retries only the failed input`, async ({
    page,
  }) => {
    await installStudioBrowserMocks(page);
    const requests: string[][] = [];
    let mode: 'partial' | 'success' | 'row-failure' | 'transport-failure' = 'partial';
    await page.route('**/api/compare', async (route) => {
      const payload = route.request().postDataJSON();
      requests.push(payload.voice_ids);
      if (mode === 'transport-failure') {
        await route.fulfill({
          status: 503,
          json: { error_code: 'GenerationError', detail: 'Synthetic transport failure.' },
        });
      } else if (mode === 'row-failure') {
        await route.fulfill({
          json: payload.voice_ids.map((voice_id: string) => ({
            voice_id,
            clip: null,
            error: { error_code: 'GenerationError', detail: 'Synthetic replacement failure.' },
          })),
        });
      } else if (mode === 'partial') {
        const response = await route.fetch({ postData: { ...payload, voice_ids: ['noir_narrator'] } });
        const results = (await response.json()) as CompareResult[];
        await route.fulfill({
          json: [
            ...results,
            {
              voice_id: 'radio_spark',
              clip: null,
              error: { error_code: failure.code, detail: failure.detail },
            },
          ],
        });
      } else {
        await route.continue();
      }
    });
    await page.goto(baseUrl);
    const alert = page.locator('.performance-deck [role="alert"]');
    await expect(alert).toHaveText('');
    await page.getByLabel('Line').fill('Keep this exact compared performance.');
    for (const id of ['noir_narrator', 'radio_spark']) {
      await page.getByRole('button', { name: `Add Test Voice (${id}) to compare` }).click();
    }
    const compared = page.waitForResponse('**/api/compare');
    await page.getByRole('button', { name: 'Compare 2', exact: true }).click();
    const [outcome] = (await (await compared).json()) as CompareResult[];
    if (!outcome.clip) throw new Error('The first compared performance must succeed.');
    const original = outcome.clip;
    const alpha = page.locator('.compare-lane[data-voice-id="noir_narrator"]');
    const beta = page.locator('.compare-lane[data-voice-id="radio_spark"]');
    await expect(alpha.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
    await expect(beta.getByText(failure.detail, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry 1', exact: true })).toBeEnabled();
    await expect(alert).toContainText('1 voice could not be compared.');
    await alpha.getByRole('button', { name: 'Play', exact: true }).click();
    await page.getByRole('button', { name: 'Save compared clips', exact: true }).click();
    const alphaWav = alpha.getByRole('link', { name: 'WAV', exact: true });
    await expect(alphaWav).toBeVisible();
    const alphaHref = await alphaWav.getAttribute('href');
    expect((await playedAudioUrls(page)).some((url) => url.endsWith(original.audio_url))).toBe(true);
    expect(await (await page.request.get(`${baseUrl}${alphaHref}`)).body()).toEqual(
      await (await page.request.get(`${baseUrl}${original.audio_url}`)).body(),
    );

    mode = 'success';
    await page.getByRole('button', { name: 'Retry 1', exact: true }).click();
    await expect(beta.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
    await expect(beta.getByText('Failed', { exact: true })).toHaveCount(0);
    expect(await alphaWav.getAttribute('href')).toBe(alphaHref);
    await alpha.getByRole('button', { name: 'Play', exact: true }).click();
    expect((await playedAudioUrls(page)).at(-1)).toContain(original.audio_url);
    expect(requests).toEqual([['noir_narrator', 'radio_spark'], ['radio_spark']]);

    // A failed replacement request must not erase the performances or their links.
    await page.getByRole('button', { name: 'Save compared clips', exact: true }).click();
    await expect(beta.getByRole('link', { name: 'WAV', exact: true })).toBeVisible();
    mode = 'row-failure';
    await page.getByLabel('Line').fill('A replacement that will fail.');
    await page.getByRole('button', { name: 'Compare 2', exact: true }).click();
    await expect(alert).toContainText('2 voices could not be compared.');
    for (const lane of [alpha, beta]) {
      await expect(lane.getByText('Original clip retained', { exact: true })).toBeVisible();
      await expect(lane.getByText('Keep this exact compared performance.', { exact: true })).toBeVisible();
      await expect(lane.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
      await expect(lane.getByRole('link', { name: 'WAV', exact: true })).toBeVisible();
    }
    expect(await alphaWav.getAttribute('href')).toBe(alphaHref);
    await expect(page.getByRole('button', { name: 'Retry 2', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Save original compared clips', exact: true })).toBeEnabled();
    mode = 'transport-failure';
    await page.getByRole('button', { name: 'Retry 2', exact: true }).click();
    await expect(alert).toHaveText('Synthetic transport failure.');
    expect(await alphaWav.getAttribute('href')).toBe(alphaHref);
    await expect(beta.getByRole('link', { name: 'WAV', exact: true })).toBeVisible();
    await expect(alpha.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
    if (failure.name === 'generation') {
      await page.screenshot({ path: path.join(screenshotDir, 'story-compare-retained.png'), fullPage: true });
    }
  });
}
