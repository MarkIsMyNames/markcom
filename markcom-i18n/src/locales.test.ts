import en from '../e2e/site/locales/en.json' with { type: 'json' };
import ga from '../e2e/site/locales/ga.json' with { type: 'json' };
import { locales } from '../e2e/site/locales.ts';
import { leafKeys, lookupString } from './locales.ts';

describe('lookupString and leafKeys', () => {
  it('read strings by dotted key', () => {
    expect(leafKeys(en)).toEqual([
      'meta.title',
      'meta.description',
      'page.heading',
      'page.welcome',
    ]);
    expect(lookupString(en, 'page.heading')).toBe('Hello');
  });

  it.each(['page.missing', 'page'])('lookupString throws for %s', (key) => {
    expect(() => lookupString(en, key)).toThrow(Error);
  });
});

describe('LocaleSet', () => {
  it('serves every language, the default first', () => {
    expect(locales.entries).toEqual([
      ['en', en],
      ['ga', ga],
    ]);
    expect(locales.defaultLocale).toBe(en);
    expect(() => locales.localeFor('xx' as 'en')).toThrow(Error);
  });

  it.each([
    [['ga-IE', 'en'], 'ga'],
    [['xx', 'en-IE'], 'en'],
    [[], 'en'],
  ])('detects %j as %s', (preferred, expected) => {
    expect(locales.detectLang(preferred)).toBe(expected);
  });

  it.each([
    ['ga', true],
    ['toString', false],
    [undefined, false],
  ])('isSupportedLang(%s) is %s', (lang, expected) => {
    expect(locales.isSupportedLang(lang)).toBe(expected);
  });

  it.each([
    ['page.heading', true],
    ['page', false],
  ])('isLocaleKey(%s) is %s', (key, expected) => {
    expect(locales.isLocaleKey(key)).toBe(expected);
  });
});
