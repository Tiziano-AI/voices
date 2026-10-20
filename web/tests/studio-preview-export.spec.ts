import { expect, type Page, test } from '@playwright/test';

import type { VoiceSummary } from '../src/lib/types';
import { installStudioBrowserMocks, playedAudioUrls } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
if (!baseUrl) throw new Error('PLAYWRIGHT_BASE_URL is required.');

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

async function prepareCompare(page: Page): Promise<void> {
  await page.goto(baseUrl);
  await page.getByLabel('Line').fill('Keep the performances that I compared.');
  await page.getByRole('button', { name: 'Add Test Voice (noir_narrator) to compare' }).click();
  await page.getByRole('button', { name: 'Add Test Voice (radio_spark) to compare' }).click();
}

test('compare pins each observed effective language even without a shared language override', async ({ page }) => {
  const voices = (await (await page.request.get(`${baseUrl}/api/voices`)).json()) as VoiceSummary[];
  const observed = voices.map((voice) => ({
    ...voice,
    language: voice.id === 'radio_spark' ? 'Italian' : 'English',
  }));
  await page.route('**/api/voices', (route) => route.fulfill({ json: observed }));
  // This boundary test observes the submitted preconditions without running synthesis.
  await page.route('**/api/compare', (route) => route.fulfill({ json: [] }));
  await prepareCompare(page);
  const requested = page.waitForRequest('**/api/compare');
  await page.getByRole('button', { name: /Compare 2/ }).click();
  const payload = (await requested).postDataJSON();
  expect(payload.language).toBeNull();
  expect(payload.expected_languages).toEqual({ noir_narrator: 'English', radio_spark: 'Italian' });
});

test('saving a preview uses its token and downloads its exact WAV', async ({ page }) => {
  const renders: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/render') renders.push(request.url());
  });
  await page.goto(baseUrl);
  await page.getByLabel('Line').fill('This is the performance to keep.');
  const generated = page.waitForResponse('**/api/preview');
  await page.getByRole('button', { name: 'Play preview' }).click();
  const clip = await (await generated).json();
  const auditioned = await (await page.request.get(`${baseUrl}${clip.audio_url}`)).body();
  const exported = page.waitForResponse(`**/api/previews/${clip.token}/export`);
  await page.getByRole('button', { name: 'Save preview' }).click();
  expect((await exported).status()).toBe(200);
  const download = page.getByRole('link', { name: 'Download WAV' });
  await expect(download).toBeVisible();
  const href = await download.getAttribute('href');
  expect(await (await page.request.get(`${baseUrl}${href}`)).body()).toEqual(auditioned);
  expect(renders).toEqual([]);
});

test('a direct render completed after edits remains an explicitly original artifact', async ({ page }) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/render', async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto(baseUrl);
  await page.getByLabel('Line').fill('The original directly rendered line.');
  const requested = page.waitForRequest('**/api/render');
  await page.getByRole('button', { name: 'Render export' }).click();
  const originalVoice = (await requested).postDataJSON().voice_id;
  await page.getByLabel('Line').fill('Edited before the original export completed.');
  const nextVoice = originalVoice === 'matteo' ? 'radio_spark' : 'matteo';
  await page.getByRole('button', { name: `Select Test Voice (${nextVoice})`, exact: true }).click();
  release();
  const output = page.locator('.output-panel').first();
  await expect(output.getByRole('link', { name: 'Download WAV' })).toBeVisible();
  await expect(output.getByText('Original clip', { exact: true })).toBeVisible();
  await expect(output.getByText('The original directly rendered line.')).toBeVisible();
  await expect(output.getByText('Original clip · Voice is not in the current selection.')).toBeVisible();
  await expect(output.getByText('Current clip', { exact: true })).toHaveCount(0);
});

test('a preview export completed after edits retains its original performance and links', async ({ page }) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/previews/*/export', async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto(baseUrl);
  await page.getByLabel('Line').fill('The original preview line.');
  await page.getByRole('button', { name: 'Play preview' }).click();
  await expect(page.getByRole('button', { name: 'Save preview' })).toBeEnabled();
  const requested = page.waitForRequest('**/api/previews/*/export');
  await page.getByRole('button', { name: 'Save preview' }).click();
  await requested;
  await page.getByLabel('Line').fill('Edited during the preview export.');
  release();
  const output = page.locator('.output-panel').first();
  await expect(output.getByRole('link', { name: 'Download WAV' })).toBeVisible();
  await expect(output.getByText('The original preview line.')).toBeVisible();
  await expect(output.getByText('Original clip · Audition text changed.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save original clip', exact: true })).toBeEnabled();
});

test('saving a board winner promotes that occurrence, never /api/render', async ({ page }) => {
  const exportedTokens: string[] = [];
  const renders: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/render') renders.push(path);
    if (path.endsWith('/export')) exportedTokens.push(path);
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Keep this board winner.');
  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(3);
  const winner = page.locator('.audition-card').first();
  await winner.getByRole('button', { name: 'Play' }).click();
  const played = await playedAudioUrls(page);
  await winner.getByRole('button', { name: 'Save clip' }).click();
  const wav = winner.getByRole('link', { name: 'WAV', exact: true });
  await expect(wav).toBeVisible();
  expect(exportedTokens).toHaveLength(1);
  const token = exportedTokens[0].split('/')[3];
  expect(played.some((url) => url.includes(`/api/assets/${token}.wav`))).toBe(true);
  expect(await (await page.request.get(`${baseUrl}${await wav.getAttribute('href')}`)).body()).toEqual(
    await (await page.request.get(`${baseUrl}/api/assets/${token}.wav`)).body(),
  );
  expect(renders).toEqual([]);
});

test('expired preview reports the failure without silently synthesizing again', async ({ page }) => {
  const renders: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/render') renders.push(request.url());
  });
  await page.route('**/api/previews/*/export', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        error_code: 'VoiceNotFoundError',
        detail: 'Preview expired or not found. Generate a new preview.',
      }),
    });
  });
  await page.goto(baseUrl);
  await page.getByLabel('Line').fill('Do not substitute a new performance.');
  await page.getByRole('button', { name: 'Play preview' }).click();
  await page.getByRole('button', { name: 'Save preview' }).click();
  await expect(page.getByText('Preview expired or not found. Generate a new preview.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Download WAV' })).toHaveCount(0);
  expect(renders).toEqual([]);
});

test('compare saves keep successful downloads through partial failure and retry', async ({ page }) => {
  await prepareCompare(page);
  const compared = page.waitForResponse('**/api/compare');
  await page.getByRole('button', { name: /Compare 2/ }).click();
  const clips = await (await compared).json();
  let failFirst = true;
  const exportPaths: string[] = [];
  const renders: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/render') renders.push(request.url());
  });
  await page.route('**/api/previews/*/export', async (route) => {
    const path = new URL(route.request().url()).pathname;
    exportPaths.push(path);
    if (failFirst && path.includes(clips[0].token)) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Synthetic export failure.' }),
      });
    } else {
      await route.continue();
    }
  });
  await page.getByRole('button', { name: 'Save compared clips' }).click();
  await expect(page.getByText(/1 compared clip\(s\) could not be saved/)).toBeVisible();
  const downloads = page.locator('.compare-lane').getByRole('link', { name: 'WAV', exact: true });
  await expect(downloads).toHaveCount(1);
  const retainedHref = await downloads.first().getAttribute('href');
  failFirst = false;
  await page.getByLabel('Line').fill('Edited after the original partial export.');
  await page.getByRole('button', { name: 'Save original compared clips' }).click();
  await expect(downloads).toHaveCount(2);
  expect(await downloads.evaluateAll((links) => links.map((link) => link.getAttribute('href')))).toContain(
    retainedHref,
  );
  expect(exportPaths).toEqual([
    `/api/previews/${clips[0].token}/export`,
    `/api/previews/${clips[1].token}/export`,
    `/api/previews/${clips[0].token}/export`,
    `/api/previews/${clips[1].token}/export`,
  ]);
  expect(renders).toEqual([]);
});
