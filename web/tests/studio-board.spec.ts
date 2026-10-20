import { expect, type Locator, type Page, test } from '@playwright/test';

import { installStudioBrowserMocks } from './support';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL;

if (!baseUrl) {
  throw new Error('PLAYWRIGHT_BASE_URL is required.');
}

test.beforeEach(async ({ page }) => {
  await installStudioBrowserMocks(page);
});

async function fillBoardText(page: Page, text = 'Every signal matters when the room goes quiet.'): Promise<void> {
  await page.getByLabel('Audition text').fill(text);
}

async function cardPosition(card: Locator): Promise<string> {
  return await card.evaluate((node) => {
    const element = node as HTMLElement;
    return `${element.style.getPropertyValue('--card-x')}:${element.style.getPropertyValue('--card-y')}`;
  });
}

test('audition board generation tolerates partial preview failure', async ({ page }) => {
  await page.route('**/api/preview', async (route) => {
    const payload = route.request().postDataJSON() as { voice_id?: string; text?: string; language?: string | null };
    if (payload.voice_id === 'radio_spark') {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error_code: 'GenerationError',
          detail: 'Synthetic radio failure.',
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto(baseUrl);
  await fillBoardText(page);
  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card')).toHaveCount(3);
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(2);
  await expect(page.locator('.audition-card[data-status="error"]')).toHaveCount(1);
  await expect(page.getByText('Synthetic radio failure.')).toBeVisible();
});

test('audition board retains original candidates and saves regenerated winners', async ({ page }) => {
  await page.goto(baseUrl);
  await fillBoardText(page, 'First board line.');
  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(3);
  const firstCard = page.locator('.audition-card').first();
  await page.getByLabel('Audition text').fill('Changed board line.');
  await expect(firstCard).toHaveAttribute('data-status', 'stale');
  await expect(firstCard.getByRole('button', { name: 'Save original clip' })).toBeEnabled();

  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(3);
  await expect(page.locator('.audition-card')).toHaveCount(6);
  const currentWinner = page.locator('.audition-card[data-current="true"]').first();
  await currentWinner.getByRole('button', { name: 'Save clip' }).click();
  await expect(currentWinner.getByRole('link', { name: 'WAV' })).toHaveAttribute('href', /\/api\/outputs\/.*\.wav/);
  await expect(currentWinner.getByRole('link', { name: 'JSON' })).toHaveAttribute('href', /\/api\/outputs\/.*\.json/);
});

test('audition board drag starts from handle while action buttons do not move cards', async ({ page }) => {
  await page.goto(baseUrl);
  await fillBoardText(page);
  await page.getByRole('button', { name: /Generate 3/ }).click();
  await expect(page.locator('.audition-card[data-status="ready"]')).toHaveCount(3);

  const firstCard = page.locator('.audition-card').first();
  const firstCardId = await firstCard.getAttribute('data-clip-id');
  const secondCard = page.locator('.audition-card').nth(1);
  const secondCardId = await secondCard.getAttribute('data-clip-id');
  if (firstCardId === null || secondCardId === null) {
    throw new Error('Expected audition card ids.');
  }
  const stableFirstCard = page.locator(`[data-clip-id="${firstCardId}"]`);
  const stableSecondCard = page.locator(`[data-clip-id="${secondCardId}"]`);
  const initialFirstPosition = await cardPosition(stableFirstCard);
  const initialSecondPosition = await cardPosition(stableSecondCard);

  await stableFirstCard.getByRole('button', { name: 'Play' }).click();
  await expect(stableFirstCard).toHaveAttribute('data-status', 'playing');
  expect(await cardPosition(stableFirstCard)).toBe(initialFirstPosition);

  await stableFirstCard.getByRole('button', { name: 'Save clip' }).click();
  await expect(stableFirstCard.getByRole('link', { name: 'WAV' })).toBeVisible();
  expect(await cardPosition(stableFirstCard)).toBe(initialFirstPosition);

  await stableFirstCard.getByRole('button', { name: /Remove/ }).click();
  await expect(stableFirstCard).toHaveCount(0);
  expect(await cardPosition(stableSecondCard)).toBe(initialSecondPosition);

  const handle = stableSecondCard.getByRole('button', { name: /Move/ });
  const handleBox = await handle.boundingBox();
  if (handleBox === null) {
    throw new Error('Expected a drag handle box.');
  }
  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(handleBox.x + handleBox.width / 2 + 64, handleBox.y + handleBox.height / 2 + 28);
  await page.mouse.up();
  expect(await cardPosition(stableSecondCard)).not.toBe(initialSecondPosition);
});
