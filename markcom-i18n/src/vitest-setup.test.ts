import { getI18n } from 'react-i18next';

describe('vitest-setup', () => {
  it('makes react-i18next return each key unchanged', async () => {
    await import('./vitest-setup.ts');
    expect(getI18n().t('page.welcome', { name: 'Aoife' })).toBe('page.welcome');
  });
});
