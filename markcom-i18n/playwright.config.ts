import { defineConfig, devices } from '@playwright/test';

const SITE_URL: string = 'http://localhost:4174';
const SERVER_TIMEOUT_MS: number = 120_000;

export default defineConfig({
  testDir: './e2e',
  forbidOnly: Boolean(process.env['CI']),
  reporter: [['html', { open: 'never' }]],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], baseURL: SITE_URL } }],
  webServer: {
    command: `npx vite e2e/site --config vite.config.ts --port ${new URL(SITE_URL).port} --strictPort`,
    url: SITE_URL,
    reuseExistingServer: !process.env['CI'],
    timeout: SERVER_TIMEOUT_MS,
  },
});
