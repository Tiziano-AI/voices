import path from 'node:path';
import { expect, type Page, type Route, test } from '@playwright/test';

import type { ModelIdentity, PreviewInput, ReferenceIdentity, UiConfig, VoiceSummary } from '../src/lib/types';
import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;
if (!baseUrl || !screenshotDir) throw new Error('The browser fixture environment is required.');

function gate() {
  let release = () => {};
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

async function observedInputs(page: Page) {
  const voices = (await (await page.request.get(`${baseUrl}/api/voices`)).json()) as VoiceSummary[];
  const config = (await (await page.request.get(`${baseUrl}/api/ui-config`)).json()) as UiConfig;
  const observed = { voices: [voices[0]], config };
  await page.route('**/api/voices', (route) => route.fulfill({ json: observed.voices }));
  await page.route('**/api/ui-config', (route) => route.fulfill({ json: observed.config }));
  return { observed, voices, config };
}

async function fulfillPerformance(route: Route, token: string) {
  const payload = route.request().postDataJSON() as {
    voice_id: string;
    text: string;
    language: string;
    expected_reference: ReferenceIdentity;
    expected_model: ModelIdentity;
  };
  const input: PreviewInput = {
    voice_id: payload.voice_id,
    text: payload.text,
    language: payload.language,
    ...payload.expected_reference,
    ...payload.expected_model,
  };
  await route.fulfill({
    json: {
      token,
      voice_id: input.voice_id,
      kind: 'generated',
      language: input.language,
      input,
      audio_url: `/api/assets/${token}.wav`,
    },
  });
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

test('Aa and BB are different targets and restoring exact text restores currentness', async ({ page }) => {
  await observedInputs(page);
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Aa');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  const card = page.locator('.audition-card');
  await expect(card).toHaveAttribute('data-generation', 'ready');
  await page.getByLabel('Audition text').fill('BB');
  await expect(card).toHaveAttribute('data-current', 'false');
  await expect(page.locator('.board-progress')).toHaveText('0 ready. 0 pending. 0 failed. 1 unattempted.');
  await expect(card.getByRole('button', { name: 'Save original clip' })).toBeEnabled();
  await page.getByLabel('Audition text').fill('Aa');
  await expect(card).toHaveAttribute('data-current', 'true');
  await expect(page.locator('.board-progress')).toHaveText('1 ready. 0 pending. 0 failed. 0 unattempted.');
});

test('observed reference WAV, transcript, language and model changes each invalidate a performance', async ({
  page,
}) => {
  const { observed, voices, config } = await observedInputs(page);
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Same words do not mean the same reference.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  const card = page.locator('.audition-card');
  await expect(card).toHaveAttribute('data-generation', 'ready');
  const changes = [
    { reference_sha256: '1'.repeat(64) },
    { reference_text_sha256: '2'.repeat(64) },
    { language: 'Italian' },
  ];
  for (const change of changes) {
    observed.voices = [{ ...voices[0], ...change }];
    await page.getByRole('button', { name: 'Refresh voices' }).click();
    await expect(card).toHaveAttribute('data-current', 'false');
    observed.voices = [voices[0]];
    await page.getByRole('button', { name: 'Refresh voices' }).click();
    await expect(card).toHaveAttribute('data-current', 'true');
  }
  observed.config = { ...config, base_model_revision: '3'.repeat(40) };
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(card.getByText('Original clip · Model changed.')).toBeVisible();
  observed.config = config;
  observed.voices = [{ ...voices[0], name: 'Renamed voice' }];
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(card).toHaveAttribute('data-current', 'true');
});

test('multiple A performances never cover B and a removed voice remains explicitly original', async ({ page }) => {
  const { observed, voices } = await observedInputs(page);
  const requested: string[] = [];
  await page.route('**/api/preview', async (route) => {
    requested.push(route.request().postDataJSON().voice_id);
    await fulfillPerformance(route, `coverage-${requested.length}`);
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('One target per voice, not one target per card.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card[data-generation="ready"]')).toHaveCount(1);
  observed.voices = [{ ...voices[0], reference_sha256: '4'.repeat(64) }];
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(page.getByRole('button', { name: 'Generate 1', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card[data-generation="ready"]')).toHaveCount(2);
  observed.voices = [observed.voices[0], voices[1]];
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(page.locator('.board-progress')).toHaveText('1 ready. 0 pending. 0 failed. 1 unattempted.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.board-progress')).toHaveText('2 ready. 0 pending. 0 failed. 0 unattempted.');
  expect(requested).toEqual([voices[0].id, voices[0].id, voices[1].id]);
  observed.voices = [voices[1]];
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(page.locator('.audition-card[data-current="false"]')).toHaveCount(2);
  await expect(page.locator('.board-progress')).toHaveText('1 ready. 0 pending. 0 failed. 0 unattempted.');
});

test('pending and failed targets are not ready; retry owns the same occurrence', async ({ page }) => {
  await observedInputs(page);
  const response = gate();
  let requests = 0;
  await page.route('**/api/preview', async (route) => {
    requests += 1;
    if (requests === 1) {
      await response.promise;
      await route.fulfill({ status: 503, json: { detail: 'A recoverable generation failure.' } });
    } else await route.continue();
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('A failed attempt is not a completed performance.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  const card = page.locator('.audition-card');
  await expect(page.locator('.board-progress')).toHaveText('0 ready. 1 pending. 0 failed. 0 unattempted.');
  const id = await card.getAttribute('data-clip-id');
  response.release();
  await expect(page.locator('.board-progress')).toHaveText('0 ready. 0 pending. 1 failed. 0 unattempted.');
  await expect(page.getByRole('button', { name: 'All attempted' })).toBeDisabled();
  await card.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(card).toHaveAttribute('data-generation', 'ready');
  await expect(card).toHaveAttribute('data-clip-id', id ?? 'missing');
  expect(requests).toBe(2);
});

test('late generation retains original identity and a removed pending card never returns', async ({ page }) => {
  await observedInputs(page);
  const response = gate();
  await page.route('**/api/preview', async (route) => {
    await response.promise;
    await route.continue();
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Original pending text.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card')).toHaveAttribute('data-generation', 'pending');
  await page.getByLabel('Audition text').fill('A new target while the original generates.');
  response.release();
  await expect(page.locator('.audition-card')).toHaveAttribute('data-generation', 'ready');
  await expect(page.locator('.audition-card')).toHaveAttribute('data-current', 'false');
  await expect(page.locator('.candidate-text')).toHaveText('Original pending text.');
  const secondResponse = gate();
  await page.route('**/api/preview', async (route) => {
    await secondResponse.promise;
    await route.continue();
  });
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card[data-generation="pending"]')).toHaveCount(1);
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(page.locator('.audition-card')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Generating…', exact: true })).toBeDisabled();
  secondResponse.release();
  await expect(page.getByRole('button', { name: 'Generate 1', exact: true })).toBeEnabled();
  await expect(page.locator('.audition-card')).toHaveCount(0);
});

test('an export survives text and voice changes and keeps the original exact WAV', async ({ page }) => {
  const { observed, voices } = await observedInputs(page);
  const exporting = gate();
  const arrived = gate();
  await page.route('**/api/previews/*/export', async (route) => {
    arrived.release();
    await exporting.promise;
    await route.continue();
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Keep this original performance, not the edited text.');
  const generated = page.waitForResponse('**/api/preview');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  const clip = await (await generated).json();
  const card = page.locator('.audition-card');
  await card.getByRole('button', { name: 'Save clip', exact: true }).click();
  await arrived.promise;
  await page.getByLabel('Audition text').fill('Different text while export is in flight.');
  observed.voices = [voices[1]];
  await page.getByRole('button', { name: 'Refresh voices' }).click();
  await expect(card).toHaveAttribute('data-current', 'false');
  await expect(card.getByRole('button', { name: /Remove/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Clear', exact: true })).toBeDisabled();
  exporting.release();
  const download = card.getByRole('link', { name: 'WAV', exact: true });
  await expect(download).toBeVisible();
  await expect(card).toHaveAttribute('data-save', 'saved');
  await expect(card.getByRole('button', { name: 'Save original clip' })).toBeEnabled();
  expect(await (await page.request.get(`${baseUrl}${await download.getAttribute('href')}`)).body()).toEqual(
    await (await page.request.get(`${baseUrl}${clip.audio_url}`)).body(),
  );
  const visibleContent = await card.evaluate((node) => node.scrollHeight <= node.clientHeight);
  expect(visibleContent, 'The original text, actions and saved links must fit the card.').toBe(true);
  await page.screenshot({ path: path.join(screenshotDir, 'story-board-original-saved.png'), fullPage: true });
});

test('an expired original board token never triggers replacement synthesis', async ({ page }) => {
  await observedInputs(page);
  const generated: string[] = [];
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname === '/api/preview' || pathname === '/api/render') generated.push(pathname);
  });
  await page.route('**/api/previews/*/export', (route) =>
    route.fulfill({ status: 404, json: { detail: 'Original preview expired.' } }),
  );
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('The original must not be replaced.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  const card = page.locator('.audition-card');
  await expect(card).toHaveAttribute('data-generation', 'ready');
  await page.getByLabel('Audition text').fill('Edited text.');
  await card.getByRole('button', { name: 'Save original clip' }).click();
  await expect(card).toHaveAttribute('data-save', 'failed');
  await expect(card.getByText('Original preview expired.')).toBeVisible();
  await expect(card).toHaveAttribute('data-generation', 'ready');
  expect(generated).toEqual(['/api/preview']);
  await expect(card.getByRole('button', { name: 'Save original clip' })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, 'story-board-original-save-failed.png'), fullPage: true });
});

test('an input conflict refreshes observation without retrying synthesis automatically', async ({ page }) => {
  const { observed, voices } = await observedInputs(page);
  let requests = 0;
  await page.route('**/api/preview', async (route) => {
    requests += 1;
    if (requests === 1) {
      observed.voices = [{ ...voices[0], reference_text_sha256: '5'.repeat(64) }];
      await route.fulfill({
        status: 409,
        json: { error_code: 'InputConflictError', detail: 'Reference changed before synthesis.' },
      });
    } else await fulfillPerformance(route, 'after-conflict');
  });
  await page.goto(baseUrl);
  await page.getByLabel('Audition text').fill('Conflicts are observations, not permission to substitute.');
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card')).toHaveAttribute('data-current', 'false');
  await expect(page.locator('.audition-card')).toHaveAttribute('data-generation', 'failed');
  await expect(page.locator('.board-progress')).toHaveText('0 ready. 0 pending. 0 failed. 1 unattempted.');
  expect(requests).toBe(1);
  await page.getByRole('button', { name: 'Generate 1', exact: true }).click();
  await expect(page.locator('.audition-card[data-current="true"]')).toHaveAttribute('data-generation', 'ready');
  expect(requests).toBe(2);
});
