import path from 'node:path';
import { expect, type Page, test } from '@playwright/test';
import { installStudioBrowserMocks, playedAudioUrls, resolveAudioPlay, setAudioPlayMode } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;

if (!baseUrl || !screenshotDir) {
  throw new Error('PLAYWRIGHT_BASE_URL and PLAYWRIGHT_SCREENSHOT_DIR are required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

async function fillLine(page: Page, text = 'Every signal matters when the room goes quiet.'): Promise<void> {
  await page.getByLabel('Line').fill(text);
}

async function fillBoardText(page: Page, text = 'Every signal matters when the room goes quiet.'): Promise<void> {
  await page.getByLabel('Audition text').fill(text);
}

async function queueCompareVoices(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Add Test Voice (noir_narrator) to compare' }).click();
  await page.getByRole('button', { name: 'Add Test Voice (radio_spark) to compare' }).click();
}

async function selectVoice(page: Page, voiceId: string): Promise<void> {
  await page
    .getByRole('list', { name: 'Saved voices' })
    .getByRole('button', { name: `Select Test Voice (${voiceId})` })
    .click();
}

test('desktop first viewport exposes the audition workbench and board', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(baseUrl);
  await expect(page.getByRole('heading', { name: 'Saved voices' })).toBeVisible();
  await expect(page.getByLabel('Line')).toBeVisible();
  await expect(page.locator('.transport-panel')).toBeVisible();
  await expect(page.locator('.audition-board')).toBeVisible();
  const boardBox = await page.locator('.audition-board').boundingBox();
  expect(boardBox).not.toBeNull();
  expect(boardBox?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(900);
  await page.screenshot({ path: path.join(screenshotDir, 'story-workbench-desktop.png'), fullPage: true });
});

test('mobile first viewport keeps the compact audition board before the library rail', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(baseUrl);
  await expect(page.locator('.audition-board')).toBeVisible();
  const boardBox = await page.locator('.audition-board').boundingBox();
  const railBox = await page.locator('.voice-rack').boundingBox();
  expect(boardBox).not.toBeNull();
  expect(railBox).not.toBeNull();
  expect(boardBox?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(844);
  expect(boardBox?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(railBox?.y ?? 0);
  await page.screenshot({ path: path.join(screenshotDir, 'story-workbench-mobile.png'), fullPage: true });
});

test('preview playback waits for the browser play promise before claiming playing', async ({ page }) => {
  await page.goto(baseUrl);
  await setAudioPlayMode(page, 'pending');
  await fillLine(page);
  await page.getByRole('button', { name: 'Play preview' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-status', 'loading');
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-source-kind', 'preview');
  await resolveAudioPlay(page);
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-status', 'playing');
  await expect.poll(() => playedAudioUrls(page)).toContainEqual(expect.stringContaining('/api/assets/'));
});

test('playback denial is visible and never masquerades as playing', async ({ page }) => {
  await page.goto(baseUrl);
  await setAudioPlayMode(page, 'block');
  await fillLine(page);
  await page.getByRole('button', { name: 'Play preview' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-status', 'blocked');
  await expect(page.getByText('Browser audio is blocked.')).toBeVisible();
  await expect(page.locator('.transport-panel')).not.toHaveAttribute('data-audio-status', 'playing');
});

test('generic playback rejection is visible and not reported as playing', async ({ page }) => {
  await page.goto(baseUrl);
  await setAudioPlayMode(page, 'reject');
  await fillLine(page);
  await page.getByRole('button', { name: 'Play preview' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-status', 'error');
  await expect(page.getByText('Synthetic playback failure.')).toBeVisible();
});

test('audio session is exclusive across preview, reference, compare, and board', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  await page.getByRole('button', { name: 'Play preview' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-source-kind', 'preview');

  await page.getByRole('button', { name: 'Listen to Test Voice (noir_narrator)' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-source-kind', 'reference');

  await queueCompareVoices(page);
  await page.getByRole('button', { name: /Compare 2/ }).click();
  await page.locator('.compare-lane').first().getByRole('button', { name: 'Play' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-source-kind', 'compare');

  await fillBoardText(page);
  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(3);
  await page.locator('.audition-card').first().getByRole('button', { name: 'Play' }).click();
  await expect(page.locator('.transport-panel')).toHaveAttribute('data-audio-source-kind', 'board');
  await expect(page.locator('.audition-card[data-status="playing"]')).toHaveCount(1);
  await expect.poll(() => playedAudioUrls(page)).toContainEqual(expect.stringContaining('/api/voices/'));
});

test('palette switch supports petrol and ember', async ({ page }) => {
  await page.goto(baseUrl);
  const palette = page.getByLabel('Palette');
  await palette.selectOption('petrol');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'petrol');
  await page.screenshot({ path: path.join(screenshotDir, 'story-theme-petrol.png'), fullPage: true });
  await palette.selectOption('ember');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'ember');
  await page.screenshot({ path: path.join(screenshotDir, 'story-theme-ember.png'), fullPage: true });
});

test('non-library load failures do not masquerade as library corruption', async ({ page }) => {
  await page.route('**/api/voices', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error_code: 'MissingDependencyError',
        detail: 'Bundled UI assets are missing.',
      }),
    });
  });

  await page.goto(baseUrl);
  await expect(page.getByRole('heading', { name: 'Load the local studio again.' })).toBeVisible();
  await expect(page.getByText('Bundled UI assets are missing.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Fix the saved library first.' })).toHaveCount(0);
});

test('compare one line across voices', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  await queueCompareVoices(page);
  await page.getByRole('button', { name: /Compare 2/ }).click();
  await expect(page.locator('.compare-lane')).toHaveCount(2);
  await expect(page.locator('.compare-lane').getByRole('button', { name: 'Play' })).toHaveCount(2);
  await page.screenshot({ path: path.join(screenshotDir, 'story-compare.png'), fullPage: true });
});

test('render export exposes persisted WAV and JSON downloads', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  await page.getByRole('button', { name: 'Render export' }).click();
  await expect(page.getByRole('link', { name: 'Download WAV' })).toHaveAttribute('href', /\/api\/outputs\/.*\.wav/);
  await expect(page.getByRole('link', { name: 'Download JSON' })).toHaveAttribute('href', /\/api\/outputs\/.*\.json/);
});

test('editing the stage line retains original performances and derives freshness reversibly', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  await queueCompareVoices(page);
  await page.getByRole('button', { name: /Compare 2/ }).click();
  await expect(page.locator('.compare-lane').getByRole('button', { name: 'Play' })).toHaveCount(2);
  await page.getByRole('button', { name: 'Play preview' }).click();
  const currentOutput = page.locator('.output-panel').first();
  await expect(currentOutput.getByRole('button', { name: 'Replay preview' })).toBeVisible();
  await page.getByLabel('Line').fill('The line changed, but the original performance remains.');
  await expect(currentOutput.getByRole('button', { name: 'Replay preview' })).toBeVisible();
  await expect(currentOutput.getByText('Original clip · Audition text changed.')).toBeVisible();
  await expect(page.locator('.compare-lane').getByRole('button', { name: 'Play' })).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Save original compared clips' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Save original clip', exact: true })).toBeEnabled();
  await fillLine(page);
  await expect(currentOutput.getByText('Current clip')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save compared clips', exact: true })).toBeEnabled();
});

test('changing the line retains a late original preview without autoplay', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  let releasePreview: (() => void) | null = null;
  const delayedPreview = new Promise<void>((resolve) => {
    releasePreview = resolve;
  });

  await page.route('**/api/preview', async (route) => {
    await delayedPreview;
    await route.continue();
  });

  const previewButton = page.locator('.action-row .primary-button');
  await previewButton.click();
  await expect(previewButton).toBeDisabled();
  await page.getByLabel('Line').fill('Changed while preview was still generating.');
  await expect(previewButton).toBeDisabled();
  releasePreview?.();
  await expect(page.locator('.output-panel').first().getByRole('button', { name: 'Replay preview' })).toBeVisible();
  await expect(page.getByText('Original clip · Audition text changed.')).toBeVisible();
  await expect(previewButton).toBeEnabled();
  expect(await playedAudioUrls(page)).toEqual([]);
});

test('opening creation abandons a late preview error', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  let releasePreview: (() => void) | null = null;
  const previewReleased = new Promise<void>((resolve) => {
    releasePreview = resolve;
  });

  await page.route('**/api/preview', async (route) => {
    await previewReleased;
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error_code: 'GenerationError',
        detail: 'Late preview failure.',
      }),
    });
  });

  await page.getByRole('button', { name: 'Play preview' }).click();
  await page.getByRole('main').getByRole('button', { name: 'Design', exact: true }).click();
  releasePreview?.();
  await page.waitForTimeout(200);
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Late preview failure.')).toHaveCount(0);
});

test('late preview responses do not overwrite a new voice selection', async ({ page }) => {
  await page.goto(baseUrl);
  await fillLine(page);
  let releasePreview: (() => void) | null = null;
  const previewReleased = new Promise<void>((resolve) => {
    releasePreview = resolve;
  });

  await page.route('**/api/preview', async (route) => {
    await previewReleased;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        token: 'late-preview',
        voice_id: 'matteo',
        kind: 'generated',
        language: 'English',
        audio_url: '/api/assets/late-preview.wav',
      }),
    });
  });

  await page.getByRole('button', { name: 'Play preview' }).click();
  const currentVoiceId = (await page.locator('.mono-chip').last().textContent())?.trim() ?? '';
  const nextVoiceId = currentVoiceId === 'matteo' ? 'radio_spark' : 'matteo';
  await selectVoice(page, nextVoiceId);
  releasePreview?.();
  await page.waitForTimeout(200);
  await expect(page.locator('.mono-chip').last()).toHaveText(nextVoiceId);
  await expect(page.locator('.output-panel').first().getByRole('button', { name: 'Replay preview' })).toHaveCount(0);
});

test('switching voices clears stale detail until the next detail payload arrives', async ({ page }) => {
  await page.goto(baseUrl);
  const currentVoiceId = (await page.locator('.mono-chip').last().textContent())?.trim() ?? '';
  const nextVoiceId = currentVoiceId === 'matteo' ? 'radio_spark' : 'matteo';
  let releaseDetail: (() => void) | null = null;
  const detailReleased = new Promise<void>((resolve) => {
    releaseDetail = resolve;
  });

  await page.route(`**/api/voices/${nextVoiceId}`, async (route) => {
    await detailReleased;
    await route.continue();
  });

  await selectVoice(page, nextVoiceId);
  await expect(page.getByRole('main').getByRole('heading', { name: 'Choose a saved voice' })).toBeVisible();
  await expect(page.locator('.mono-chip').last()).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Details', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Reference', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Play preview' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Render export' })).toBeDisabled();

  releaseDetail?.();
  await expect(page.locator('.mono-chip').last()).toHaveText(nextVoiceId);
});
