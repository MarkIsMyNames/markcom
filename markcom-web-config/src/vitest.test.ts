import { describe, expect, it } from 'vitest';
import { coverageGate } from './vitest.ts';

describe('coverageGate', () => {
  it.each(['lines', 'branches', 'functions', 'statements'] as const)(
    'sets the %s threshold to the gate',
    (metric: 'lines' | 'branches' | 'functions' | 'statements') => {
      const { thresholds } = coverageGate({ include: [], exclude: [] });
      expect(thresholds).toMatchObject({ [metric]: 85 });
    },
  );

  it.each([
    { include: ['src/**/*.ts'], exclude: ['src/**/*.test.ts'] },
    { include: [], exclude: [] },
  ])(
    'passes include and exclude through for $include',
    (files: { include: string[]; exclude: string[] }) => {
      expect(coverageGate(files)).toMatchObject(files);
    },
  );

  it('uses the v8 provider', () => {
    expect(coverageGate({ include: [], exclude: [] }).provider).toBe('v8');
  });
});
