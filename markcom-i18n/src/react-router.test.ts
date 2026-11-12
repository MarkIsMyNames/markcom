import { createMemoryRouter } from 'react-router';
import { locales } from '../e2e/site/locales.ts';
import { languageRoutes } from './react-router.ts';

/** Opens `path` with stubs for i18next, the browser languages and the page. */
async function open(path: string, preferred: readonly string[]) {
  const i18n = { changeLanguage: vi.fn(() => Promise.resolve()) };
  const documentElement = { lang: '' };
  const router = createMemoryRouter(
    languageRoutes({
      locales,
      i18n,
      rootPath: '/',
      preferredLanguages: () => preferred,
      documentElement,
      layout: null,
      children: [],
    }),
    { initialEntries: [path] },
  );
  await vi.waitFor(() => {
    expect(router.state.navigation.state === 'idle' && router.state.initialized).toBe(true);
  });
  return { path: router.state.location.pathname, i18n, documentElement };
}

describe('languageRoutes', () => {
  it.each([
    ['/', ['ga-IE'], '/ga'],
    ['/', ['fr'], '/en'],
    ['/xx', ['ga'], '/ga'],
  ])('sends %s with preferences %j to %s', async (path, preferred, expected) => {
    expect((await open(path, preferred)).path).toBe(expected);
  });

  it('switches i18next and the page language to the URL language', async () => {
    const { path, i18n, documentElement } = await open('/ga', ['en']);
    expect(path).toBe('/ga');
    expect(i18n.changeLanguage).toHaveBeenCalledWith('ga');
    expect(documentElement.lang).toBe('ga');
  });
});
