import { match } from '@formatjs/intl-localematcher';
import { flattenObject } from 'es-toolkit';
import type { ParseKeys } from 'i18next';

export type LocaleValue = string | LocaleRecord;
export type LocaleRecord = { readonly [key: string]: LocaleValue };

/** Joins a key to the path of the record it sits in. */
const KEY_SEPARATOR: string = '.';

/** Every dotted key path that ends in a string, with its string. */
export function flattenLocale(locale: LocaleRecord): ReadonlyMap<string, string> {
  return new Map(
    Object.entries<unknown>(flattenObject(locale, { delimiter: KEY_SEPARATOR })).flatMap(
      ([key, value]: [string, unknown]): [string, string][] =>
        typeof value === 'string' ? [[key, value]] : [],
    ),
  );
}

/** The string at a dotted key path; throws if missing or not a string. */
export function lookupString(locale: LocaleRecord, key: string): string {
  const value: string | undefined = flattenLocale(locale).get(key);
  if (value === undefined) {
    throw new Error(`Locale key is missing or not a string: ${key}`);
  }
  return value;
}

/** Every dotted key path that ends in a string. */
export function leafKeys(locale: LocaleRecord): string[] {
  return [...flattenLocale(locale).keys()];
}

/** A site's languages and their locale files; the default locale holds the full key set. */
export class LocaleSet<Lang extends string, Locale extends LocaleRecord> {
  readonly defaultLang: Lang;
  readonly defaultLocale: Locale;
  readonly langs: readonly Lang[];
  private readonly locales: ReadonlyMap<Lang, Locale>;

  constructor(locales: Readonly<Record<Lang, Locale>>, defaultLang: NoInfer<Lang>) {
    const isLang: (key: string) => key is Lang = (key: string): key is Lang =>
      Object.hasOwn(locales, key);
    this.locales = new Map(
      Object.entries<Locale>(locales).flatMap(
        ([lang, locale]: [string, Locale]): [Lang, Locale][] =>
          isLang(lang) ? [[lang, locale]] : [],
      ),
    );
    this.langs = [...this.locales.keys()];
    this.defaultLang = defaultLang;
    this.defaultLocale = this.localeFor(defaultLang);
  }

  get entries(): readonly (readonly [Lang, Locale])[] {
    return [...this.locales.entries()];
  }

  localeFor(lang: Lang): Locale {
    const locale: Locale | undefined = this.locales.get(lang);
    if (locale === undefined) {
      throw new Error(`No locale for language: ${lang}`);
    }
    return locale;
  }

  isSupportedLang(lang: string | undefined): lang is Lang {
    return this.langs.some((supported: Lang): boolean => supported === lang);
  }

  /** The best supported match for the browser's preferences, else the default. */
  detectLang(preferred: readonly string[]): Lang {
    // match() only ever returns one of the supported languages or the default it was given.
    return match(preferred, this.langs, this.defaultLang) as Lang;
  }

  /** True for a key of the default locale. ViewModels hold these; views turn them into text. */
  isLocaleKey(key: string): key is ParseKeys {
    return leafKeys(this.defaultLocale).includes(key);
  }
}
