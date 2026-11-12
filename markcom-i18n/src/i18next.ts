import i18next, { type i18n as I18next, type Resource } from 'i18next';
import { initReactI18next } from 'react-i18next';
import type { LocaleRecord, LocaleSet } from './locales.js';

/** A ready i18next instance serving every locale, starting in the default language. */
export async function createI18n<Lang extends string, Locale extends LocaleRecord>(
  locales: LocaleSet<Lang, Locale>,
): Promise<I18next> {
  const instance: I18next = i18next.createInstance();
  const resources: Resource = Object.fromEntries(
    locales.entries.map(
      ([lang, translation]: readonly [Lang, Locale]): [Lang, { translation: Locale }] => [
        lang,
        { translation },
      ],
    ),
  );
  await instance.use(initReactI18next).init({
    resources,
    lng: locales.defaultLang,
    fallbackLng: locales.defaultLang,
    // React escapes rendered text already.
    interpolation: { escapeValue: false },
  });
  return instance;
}
