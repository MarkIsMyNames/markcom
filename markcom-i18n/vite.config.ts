import { coverageGate } from '@markcom/web-config/vitest';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { locales } from './e2e/site/locales.ts';
import { localeHtmlPlugin } from './src/vite.ts';

/** Serves the test site in e2e/site for Playwright; runs the unit tests in src/ for Vitest. */
export default defineConfig({
  plugins: [react(), localeHtmlPlugin({ locales, values: new Map() })],
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: coverageGate({ include: ['src/**/*.ts'], exclude: ['src/**/*.test.ts'] }),
  },
});
