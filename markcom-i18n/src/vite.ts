import { checkInvalidTranslations, checkMissingTranslations } from '@lingual/i18n-check';
import escapeHtml from 'escape-html';
import { flatten } from 'flat';
import type { Plugin } from 'vite';
import { leafKeys, lookupString, type LocaleRecord, type LocaleSet } from './locales.js';

/** index.html placeholders filled by localeHtmlPlugin. */
const HTML_PLACEHOLDER: RegExp = /\{\{[\w:.]+\}\}/g;
const TEXT_BETWEEN_TAGS: RegExp = /(?<=>)[^<>]+(?=<)/g;
const TEXT_ATTRIBUTE: RegExp =
  /(?<= (?:content|title|alt|aria-label|aria-description|placeholder)=")[^"]*(?=")/g;
const HEX_COLOUR: RegExp = /#[0-9a-f]{3,8}\b/gi;
const CHECK_OPTIONS: { format: 'i18next' } = { format: 'i18next' };
/** Meta content that is configuration, not text a person reads. */
const ALLOWED_META_CONTENT: ReadonlySet<string> = new Set(['width=device-width, initial-scale=1']);

/** i18n-check compares flat files: one dotted key per string. */
function flat(locale: LocaleRecord): Record<string, string> {
  return flatten<LocaleRecord, Record<string, string>>(locale);
}

function withoutPlaceholders(text: string): string {
  return text.replace(HTML_PLACEHOLDER, '').trim();
}

/** Keys whose string is blank. */
function findBlankStrings(locale: LocaleRecord): string[] {
  return leafKeys(locale).filter((key: string): boolean => lookupString(locale, key).trim() === '');
}

function keysMissingFrom(target: LocaleRecord, source: LocaleRecord): string[] {
  return Object.values(
    checkMissingTranslations(flat(source), { target: flat(target) }, CHECK_OPTIONS),
  ).flat();
}

/** Keys the default locale has and this locale lacks. */
function findMissingKeys(defaultLocale: LocaleRecord, locale: LocaleRecord): string[] {
  return keysMissingFrom(locale, defaultLocale);
}

/** Keys this locale has and the default locale lacks. */
function findExtraKeys(defaultLocale: LocaleRecord, locale: LocaleRecord): string[] {
  return keysMissingFrom(defaultLocale, locale);
}

/** Keys whose interpolation placeholders or nesting differ from the default locale. */
function findInvalidTranslations(defaultLocale: LocaleRecord, locale: LocaleRecord): string[] {
  return Object.values(
    checkInvalidTranslations(flat(defaultLocale), { locale: flat(locale) }, CHECK_OPTIONS),
  )
    .flat()
    .map(({ key }: { key: string }): string => key);
}

/** Text in index.html a person would read that does not come from a locale placeholder. */
function findLiteralHtmlText(html: string): string[] {
  const betweenTags: string[] = [...html.matchAll(TEXT_BETWEEN_TAGS)].map(
    ([text]: RegExpExecArray): string => text,
  );
  const inAttributes: string[] = [...html.matchAll(TEXT_ATTRIBUTE)]
    .map(([value]: RegExpExecArray): string => value)
    .filter((value: string): boolean => !ALLOWED_META_CONTENT.has(value));
  return [...betweenTags, ...inAttributes]
    .map(withoutPlaceholders)
    .filter((text: string): boolean => text !== '');
}

/** Colours written into index.html instead of coming from the tokens. */
function findHtmlColours(html: string): string[] {
  return [...html.matchAll(HEX_COLOUR)].map(([colour]: RegExpExecArray): string => colour);
}

/** Every problem in a site's locale files, one message each; empty when they are all fine. */
function findLocaleProblems<Lang extends string, Locale extends LocaleRecord>(
  locales: LocaleSet<Lang, Locale>,
): string[] {
  const defaultFile: string = `${locales.defaultLang}.json`;
  const blank: string[] = findBlankStrings(locales.defaultLocale).map(
    (key: string): string => `${defaultFile}: ${key} is blank`,
  );
  const translations: string[] = locales.langs
    .filter((lang: Lang): boolean => lang !== locales.defaultLang)
    .flatMap((lang: Lang): string[] => {
      const locale: Locale = locales.localeFor(lang);
      const file: string = `${lang}.json`;
      return [
        ...findMissingKeys(locales.defaultLocale, locale).map(
          (key: string): string => `${file}: ${key} is missing`,
        ),
        ...findExtraKeys(locales.defaultLocale, locale).map(
          (key: string): string => `${file}: ${key} is not in ${defaultFile}`,
        ),
        ...findInvalidTranslations(locales.defaultLocale, locale).map(
          (key: string): string => `${file}: ${key} has different placeholders from ${defaultFile}`,
        ),
      ];
    });
  return [...blank, ...translations];
}

/** Every problem in a site's index.html, one message each; empty when it is fine. */
function findIndexHtmlProblems(html: string): string[] {
  return [
    ...findLiteralHtmlText(html).map(
      (text: string): string => `index.html: "${text}" is literal text; use {{t:key}}`,
    ),
    ...findHtmlColours(html).map(
      (colour: string): string => `index.html: ${colour} is a hard-coded colour; use {{name}}`,
    ),
  ];
}

/** `{{t:meta.title}}` inserts a locale string; `{{lang}}` inserts a named value. */
const PLACEHOLDER: RegExp = /\{\{(t:)?([\w.]+)\}\}/g;
const PLUGIN_NAME: string = 'markcom-locale-html';

export type LocaleHtmlOptions<Lang extends string, Locale extends LocaleRecord> = {
  locales: LocaleSet<Lang, Locale>;
  /** Values for `{{name}}` placeholders, such as the theme colour. `{{lang}}` is filled in. */
  values: ReadonlyMap<string, string>;
};

function resolveValue(values: ReadonlyMap<string, string>, name: string): string {
  const value: string | undefined = values.get(name);
  if (value === undefined) {
    throw new Error(`index.html placeholder {{${name}}} has no value`);
  }
  return value;
}

function failOnProblems(problems: readonly string[]): void {
  if (problems.length > 0) {
    throw new Error(`Locale problems:\n${problems.join('\n')}`);
  }
}

/** Replaces every placeholder in index.html, HTML-escaped; fails on an unknown key or value. */
function renderLocaleHtml(
  html: string,
  locale: LocaleRecord,
  values: ReadonlyMap<string, string>,
): string {
  return html.replace(
    PLACEHOLDER,
    (_match: string, localePrefix: string | undefined, key: string): string =>
      escapeHtml(
        localePrefix === undefined ? resolveValue(values, key) : lookupString(locale, key),
      ),
  );
}

/**
 * Fills index.html from the default locale, and stops `vite` and `vite build` when a locale
 * file is incomplete or index.html has text or colours that do not come from a placeholder.
 */
export function localeHtmlPlugin<Lang extends string, Locale extends LocaleRecord>(
  options: LocaleHtmlOptions<Lang, Locale>,
): Plugin {
  const values: ReadonlyMap<string, string> = new Map([
    ['lang', options.locales.defaultLang],
    ...options.values,
  ]);
  return {
    name: PLUGIN_NAME,
    buildStart: (): void => {
      failOnProblems(findLocaleProblems(options.locales));
    },
    transformIndexHtml: {
      // Before Vite adds its own scripts, so only the site's index.html is checked.
      order: 'pre',
      handler: (html: string): string => {
        failOnProblems(findIndexHtmlProblems(html));
        return renderLocaleHtml(html, options.locales.defaultLocale, values);
      },
    },
  };
}
