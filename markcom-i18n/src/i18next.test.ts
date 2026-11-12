import { locales } from '../e2e/site/locales.ts';
import { createI18n } from './i18next.ts';

describe('createI18n', () => {
  it('starts in the default language and serves every language', async () => {
    const i18n = await createI18n(locales);
    expect(i18n.t('page.welcome', { name: 'Aoife' })).toBe('Welcome, Aoife');
    await i18n.changeLanguage('ga');
    expect(i18n.t('page.welcome', { name: 'Aoife' })).toBe('Fáilte, Aoife');
  });
});
