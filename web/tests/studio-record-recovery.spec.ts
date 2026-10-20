import { readFile } from 'node:fs/promises';
import { expect, type Page, test } from '@playwright/test';
import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;
if (!baseUrl) {
  throw new Error('PLAYWRIGHT_BASE_URL is required.');
}

interface CaptureProbe {
  deferred: boolean;
  requests: number;
  activeTracks: number;
  startedRecorders: number;
  stoppedRecorders: number;
  grantNext: () => void;
}
type CaptureWindow = Window & { __captureProbe: CaptureProbe };

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
  await page.addInitScript(() => {
    const pending: Array<() => void> = [];
    const probe = {
      deferred: false,
      requests: 0,
      activeTracks: 0,
      startedRecorders: 0,
      stoppedRecorders: 0,
      grantNext: () => pending.shift()?.(),
    };
    (window as unknown as CaptureWindow).__captureProbe = probe;
    navigator.mediaDevices.getUserMedia = async () => {
      probe.requests += 1;
      return await new Promise<MediaStream>((resolve) => {
        const grant = () => {
          probe.activeTracks += 1;
          let stopped = false;
          const track = {
            stop() {
              if (!stopped) {
                probe.activeTracks -= 1;
                stopped = true;
              }
            },
          };
          resolve({ getTracks: () => [track] } as unknown as MediaStream);
        };
        if (probe.deferred) {
          pending.push(grant);
        } else {
          grant();
        }
      });
    };
    const originalStart = MediaRecorder.prototype.start;
    MediaRecorder.prototype.start = function (timeslice) {
      probe.startedRecorders += 1;
      originalStart.call(this, timeslice);
    };
    const originalStop = MediaRecorder.prototype.stop;
    MediaRecorder.prototype.stop = function () {
      probe.stoppedRecorders += 1;
      this.ondataavailable?.call(this, {
        data: new Blob(['synthetic-take-bytes'], { type: 'audio/webm' }),
      } as BlobEvent);
      originalStop.call(this);
    };
  });
});

async function openRecorder(page: Page) {
  await page.goto(baseUrl as string);
  await page.getByRole('main').getByRole('button', { name: 'Record live', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Capture mode').selectOption('free');
  return dialog;
}

test('closing during microphone permission retires a late stream without starting capture', async ({ page }) => {
  const dialog = await openRecorder(page);
  await page.evaluate(() => {
    (window as unknown as CaptureWindow).__captureProbe.deferred = true;
  });
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Requesting mic…', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.grantNext());
  await expect
    .poll(() => page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.activeTracks))
    .toBe(0);
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.startedRecorders)).toBe(0);
});

test('reset invalidates an older permission request without retiring the new capture', async ({ page }) => {
  const dialog = await openRecorder(page);
  await page.evaluate(() => {
    (window as unknown as CaptureWindow).__captureProbe.deferred = true;
  });
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Reset', exact: true }).click();
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.requests)).toBe(2);
  await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.grantNext());
  await expect(dialog.getByRole('button', { name: 'Requesting mic…', exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.activeTracks)).toBe(0);
  await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.grantNext());
  await expect(dialog.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.startedRecorders)).toBe(1);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.activeTracks))
    .toBe(0);
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.stoppedRecorders)).toBe(1);
});

test('failed review keeps the captured bytes for download and an explicit retry', async ({ page }) => {
  const postedTakes: string[] = [];
  await page.route('**/api/clone/review', async (route) => {
    const body = route.request().postDataBuffer()?.toString() ?? '';
    postedTakes.push(body.match(/Content-Type: audio\/webm\r\n\r\n([\s\S]*?)\r\n--/)?.[1] ?? '');
    if (postedTakes.length === 1) {
      await route.fulfill({ status: 503, json: { detail: 'Synthetic transcript service failure.' } });
      return;
    }
    await route.fulfill({
      json: {
        review_token: 'recovered-take',
        suggested_voice_id: 'recovered-voice',
        transcript: 'Synthetic test transcript.',
        language: 'English',
        duration_seconds: 4,
        segments: [],
        audio_url: '/api/assets/recovered-take.wav',
      },
    });
  });
  const dialog = await openRecorder(page);
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Retry review', exact: true })).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Start recording', exact: true })).toBeDisabled();
  const downloadEvent = page.waitForEvent('download');
  await dialog.getByRole('link', { name: 'Download take', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('recorded-take.webm');
  expect(await readFile((await download.path()) as string, 'utf8')).toBe(postedTakes[0]);
  expect(postedTakes[0]).toContain('synthetic-take-bytes');
  expect(postedTakes).toHaveLength(1);
  await dialog.getByRole('button', { name: 'Retry review', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save recording', exact: true })).toBeVisible();
  expect(postedTakes).toHaveLength(2);
  expect(postedTakes[1]).toBe(postedTakes[0]);
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.requests)).toBe(1);
  expect(await page.evaluate(() => (window as unknown as CaptureWindow).__captureProbe.activeTracks)).toBe(0);
});

test('reset explicitly discards a failed take and permits a new recording', async ({ page }) => {
  await page.route('**/api/clone/review', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Synthetic transcript service failure.' } }),
  );
  const dialog = await openRecorder(page);
  await dialog.getByRole('button', { name: 'Start recording', exact: true }).click();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Retry review', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(dialog.getByRole('link', { name: 'Download take', exact: true })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Start recording', exact: true })).toBeEnabled();
});
