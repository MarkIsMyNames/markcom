import type { CoverageOptions } from 'vitest/node';

/** The house coverage gate, in percent, for lines, branches, functions and statements alike. */
const COVERAGE_GATE: number = 85;

export type CoverageFiles = {
  /** The source files coverage is measured over. */
  include: string[];
  /** Files with no logic to test (styles, stories, constants) or tested another way. */
  exclude: string[];
};

/** Vitest's `test.coverage`: V8 coverage that fails the run below the house gate. */
export function coverageGate(files: CoverageFiles): CoverageOptions {
  return {
    provider: 'v8',
    include: files.include,
    exclude: files.exclude,
    thresholds: {
      lines: COVERAGE_GATE,
      branches: COVERAGE_GATE,
      functions: COVERAGE_GATE,
      statements: COVERAGE_GATE,
    },
  };
}
