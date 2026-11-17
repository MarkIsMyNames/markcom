import en from '../e2e/site/locales/en.json' with { type: 'json' };
import ga from '../e2e/site/locales/ga.json' with { type: 'json' };
import { locales } from '../e2e/site/locales.ts';
import type { IndexHtmlTransformContext } from 'vite';
import { LocaleSet, type LocaleRecord } from './locales.ts';
import { localeHtmlPlugin } from './vite.ts';

/** Calls the plugin's hooks directly, as Vite would. */
function plugin(site: LocaleSet<string, LocaleRecord>) {
  const hooks = localeHtmlPlugin({ locales: site, values: new Map([['colour', 'white']]) });
  return {
    buildStart: (hooks.buildStart as () => void).bind(hooks),
    transform: (html: string, path = '/index.html') =>
      (
        hooks.transformIndexHtml as {
          handler: (html: string, context: IndexHtmlTransformContext) => string;
        }
      ).handler(html, { path, filename: `/site${path}` }),
  };
}

describe('localeHtmlPlugin', () => {
  it('fills index.html from the default locale, escaped, with its language and values', () => {
    expect(
      plugin(locales).transform(
        '<html lang="{{lang}}"><meta name="viewport" content="width=device-width, initial-scale=1" />' +
          '<meta content="{{colour}}" /><title>{{t:meta.title}}</title>',
      ),
    ).toBe(
      '<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1" />' +
        '<meta content="white" /><title>Languages &amp; routing test site</title>',
    );
  });

  it('names every literal text and colour in index.html', () => {
    expect(() =>
      plugin(locales).transform('<title>My Site</title><img alt="A photo" /><b style="#fff">'),
    ).toThrow(
      [
        'Locale problems:',
        'index.html: "My Site" is literal text; use {{t:key}}',
        'index.html: "A photo" is literal text; use {{t:key}}',
        'index.html: #fff is a hard-coded colour; use {{name}}',
      ].join('\n'),
    );
  });

  it("leaves other HTML pages, such as Storybook's iframe.html, as they are", () => {
    const html = '<title>Storybook</title><div>{__VITEST_INJECTOR__}</div>';
    expect(plugin(locales).transform(html, '/iframe.html')).toBe(html);
  });

  it.each([
    ['an unknown locale key', '<title>{{t:meta.missing}}</title>'],
    ['an unknown value', '<meta content="{{missing}}" />'],
  ])('rejects index.html with %s', (_case, html) => {
    expect(() => plugin(locales).transform(html)).toThrow(Error);
  });

  it('starts when every locale is complete', () => {
    expect(plugin(locales).buildStart).not.toThrow();
  });

  it('stops the build naming the file and key of every locale problem', () => {
    const blankEn = { ...en, page: { ...en.page, heading: ' ' } };
    const brokenGa = { ...ga, page: { welcome: 'Fáilte, {{ainm}}', extra: 'x' } };
    expect(plugin(new LocaleSet({ en: blankEn, ga: brokenGa }, 'en')).buildStart).toThrow(
      [
        'Locale problems:',
        'en.json: page.heading is blank',
        'ga.json: page.heading is missing',
        'ga.json: page.extra is not in en.json',
        'ga.json: page.welcome has different placeholders from en.json',
      ].join('\n'),
    );
  });
});
