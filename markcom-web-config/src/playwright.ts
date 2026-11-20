import {
  defineConfig,
  devices,
  expect,
  test,
  type APIRequestContext,
  type Page,
  type PlaywrightTestConfig,
} from '@playwright/test';

import { APP_URL, STORYBOOK_URL } from './config.js';

const SERVER_TIMEOUT_MS: number = 120_000;

type StoryEntry = { id: string; type: string };
type StoryIndex = { entries: Record<string, StoryEntry> };

/**
 * The react-ui websites' Playwright config. `visual` screenshots every Storybook story;
 * `e2e` drives the built app, for integration tests when they are asked for.
 */
export function createPlaywrightConfig(): PlaywrightTestConfig {
  return defineConfig({
    forbidOnly: Boolean(process.env['CI']),
    reporter: [['html', { open: 'never' }]],
    snapshotPathTemplate: '{testDir}/__snapshots__/{arg}{ext}',
    // threshold 0.2 (the default) lets a colour of similar brightness through; 0.05 still ignores anti-aliasing.
    expect: { toHaveScreenshot: { animations: 'disabled', caret: 'hide', threshold: 0.05 } },
    projects: [
      {
        name: 'visual',
        testDir: './visual',
        use: { ...devices['Desktop Chrome'], baseURL: STORYBOOK_URL },
      },
      {
        name: 'e2e',
        testDir: './e2e',
        use: { ...devices['Desktop Chrome'], baseURL: APP_URL },
      },
    ],
    // When e2e tests are asked for, also serve the built app (npm run preview) for that project.
    webServer: {
      command: 'npx vite preview --outDir storybook-static --port 6006 --strictPort',
      url: STORYBOOK_URL,
      reuseExistingServer: !process.env['CI'],
      timeout: SERVER_TIMEOUT_MS,
    },
  });
}

/** One screenshot per story; any pixel difference from the committed baseline fails. */
export function testStoryScreenshots(): void {
  test('every story matches its baseline', async ({
    page,
    request,
  }: {
    page: Page;
    request: APIRequestContext;
  }): Promise<void> => {
    const index: StoryIndex = (await (await request.get('/index.json')).json()) as StoryIndex;
    const storyIds: string[] = Object.values(index.entries)
      .filter((entry: StoryEntry): boolean => entry.type === 'story')
      .map((entry: StoryEntry): string => entry.id);

    for (const id of storyIds) {
      await test.step(id, async (): Promise<void> => {
        await page.goto(`/iframe.html?id=${id}&viewMode=story`);
        await page.locator('#storybook-root').waitFor();
        await page.evaluate((): Promise<FontFaceSet> => document.fonts.ready);
        await expect.soft(page).toHaveScreenshot(`${id}.png`, { fullPage: true });
      });
    }
  });
}
