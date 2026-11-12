import { expect, test } from '@playwright/test';
import { lookupString } from '../src/locales.ts';
import { locales } from './site/locales.ts';

test.use({ locale: 'ga-IE' });

test('sends the root path to the browser language', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL('/ga');
});

test('sends an unsupported language to the browser language', async ({ page }) => {
  await page.goto('/xx');
  await expect(page).toHaveURL('/ga');
});

for (const lang of locales.langs) {
  test(`serves ${lang} in ${lang}`, async ({ page }) => {
    await page.goto(`/${lang}`);
    await expect(page.locator('html')).toHaveAttribute('lang', lang);
    await expect(
      page.getByRole('heading', { name: lookupString(locales.localeFor(lang), 'page.heading') }),
    ).toBeVisible();
  });
}

test('fills the title and description from the default locale', async ({ page }) => {
  await page.goto('/en');
  await expect(page).toHaveTitle(lookupString(locales.defaultLocale, 'meta.title'));
  await expect(page.locator('meta[name="description"]')).toHaveAttribute(
    'content',
    lookupString(locales.defaultLocale, 'meta.description'),
  );
});
