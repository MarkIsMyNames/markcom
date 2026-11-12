import type { ComponentType } from 'react';
import { redirect, type LoaderFunctionArgs, type RouteObject } from 'react-router';
import type { LocaleRecord, LocaleSet } from './locales.js';

/** The one thing routing needs from i18next, so tests can pass a fake. */
export interface LanguageSwitcher {
  changeLanguage(lang: string): Promise<unknown>;
}

export type LanguageRoutesOptions<Lang extends string, Locale extends LocaleRecord> = {
  locales: LocaleSet<Lang, Locale>;
  i18n: LanguageSwitcher;
  /** The site's root path, usually `/`. */
  rootPath: string;
  /** The browser's language preferences: `() => navigator.languages`. */
  preferredLanguages: () => readonly string[];
  /** Gets the page language: `document.documentElement`. */
  documentElement: { lang: string };
  /** Renders around every page of a language; its Outlet shows the children. */
  layout: ComponentType | null;
  children: RouteObject[];
};

/**
 * The `/<lang>/…` route: a supported language switches i18next and the page language before
 * rendering; no language or an unsupported one redirects to the one detectLang picks.
 */
export function languageRoutes<Lang extends string, Locale extends LocaleRecord>(
  options: LanguageRoutesOptions<Lang, Locale>,
): RouteObject[] {
  const { locales, rootPath }: LanguageRoutesOptions<Lang, Locale> = options;
  return [
    {
      path: `${rootPath}:lang?`,
      Component: options.layout,
      loader: async ({ params }: LoaderFunctionArgs): Promise<Response | null> => {
        const { lang }: { lang?: string } = params;
        if (!locales.isSupportedLang(lang)) {
          return redirect(`${rootPath}${locales.detectLang(options.preferredLanguages())}`);
        }
        await options.i18n.changeLanguage(lang);
        options.documentElement.lang = lang;
        return null;
      },
      children: options.children,
    },
  ];
}
