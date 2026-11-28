import { defineConfig, devices, type PlaywrightTestConfig } from '@playwright/test';

import { APP_URL, STORYBOOK_URL } from './config.js';

const SERVER_TIMEOUT_MS: number = 120_000;

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
    webServer: {
      command: `npx vite preview --outDir storybook-static --port ${new URL(STORYBOOK_URL).port} --strictPort`,
      url: STORYBOOK_URL,
      reuseExistingServer: !process.env['CI'],
      timeout: SERVER_TIMEOUT_MS,
    },
  });
}
