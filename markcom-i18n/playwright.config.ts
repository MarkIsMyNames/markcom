import { defineConfig, devices } from '@playwright/test';

const SITE_URL: string = 'http://localhost:4174';
const SERVER_TIMEOUT_MS: number = 120_000;

/** Drives the test site in e2e/site through the real browser routing. */
export default defineConfig({
  testDir: './e2e',
  forbidOnly: Boolean(process.env['CI']),
  reporter: [['html', { open: 'never' }]],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], baseURL: SITE_URL } }],
  webServer: {
    command: 'npx vite e2e/site --config vite.config.ts --port 4174 --strictPort',
    url: SITE_URL,
    reuseExistingServer: !process.env['CI'],
    timeout: SERVER_TIMEOUT_MS,
  },
});
