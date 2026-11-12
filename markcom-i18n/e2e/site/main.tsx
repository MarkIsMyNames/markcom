import { createRoot } from 'react-dom/client';
import { useTranslation } from 'react-i18next';
import { createBrowserRouter, Outlet, RouterProvider } from 'react-router';
import { createI18n } from '../../src/i18next.ts';
import { languageRoutes } from '../../src/react-router.ts';
import { locales } from './locales.ts';

function Layout() {
  const { t } = useTranslation();
  return (
    <main>
      <h1>{t('page.heading')}</h1>
      <Outlet />
    </main>
  );
}

const i18n = await createI18n(locales);
const router = createBrowserRouter(
  languageRoutes({
    locales,
    i18n,
    rootPath: '/',
    preferredLanguages: () => navigator.languages,
    documentElement: document.documentElement,
    layout: Layout,
    children: [],
  }),
);
const root = document.getElementById('root');
if (root === null) {
  throw new Error('index.html has no #root element');
}
createRoot(root).render(<RouterProvider router={router} />);
