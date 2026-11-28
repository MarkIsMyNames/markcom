import { defineConfig } from 'vitest/config';
import { coverageGate } from './src/vitest.ts';

export default defineConfig({
  test: {
    environment: 'node',
    testTimeout: 60_000, // type-aware linting is slow on first run
    include: ['src/**/*.test.ts'],
    coverage: coverageGate({
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/config.ts', 'src/story-screenshots.ts'],
    }),
  },
});
