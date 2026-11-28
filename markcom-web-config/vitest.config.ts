import { defineConfig } from 'vitest/config';
import { coverageGate } from './src/vitest.ts';

export default defineConfig({
  test: {
    testTimeout: 60_000, // type-aware linting is slow on first run
    include: ['src/**/*.test.ts'],
    coverage: coverageGate({
      include: ['src/**/*.ts'],
      // story-screenshots runs only under Playwright, which Vitest can't cover
      exclude: ['src/**/*.test.ts', 'src/config.ts', 'src/story-screenshots.ts'],
    }),
  },
});
