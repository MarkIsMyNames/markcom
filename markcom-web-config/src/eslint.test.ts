import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';
import { createEslintConfig } from './eslint.ts';

const ROOT: string = new URL('..', import.meta.url).pathname;

async function ruleIds(code: string, file: string): Promise<(string | null)[]> {
  const eslint: ESLint = new ESLint({
    cwd: ROOT,
    overrideConfigFile: true,
    overrideConfig: createEslintConfig({ tsconfigRootDir: ROOT }),
  });
  const [result] = await eslint.lintText(code, { filePath: `${ROOT}${file}` });
  return result?.messages.map((m) => m.ruleId) ?? [];
}

describe('createEslintConfig', () => {
  it.each([
    {
      name: 'a magic number',
      code: 'export const x: number = Math.max(42, 1);\n',
      rule: '@typescript-eslint/no-magic-numbers',
    },
    {
      name: 'an unannotated variable',
      code: 'export const x = 0;\n',
      rule: 'no-restricted-syntax',
    },
  ])('reports $name in source', async ({ code, rule }: { code: string; rule: string }) => {
    expect(await ruleIds(code, 'src/eslint.ts')).toContain(rule);
  });

  it('accepts a clean snippet', async () => {
    expect(await ruleIds('export const x: number = 1;\n', 'src/eslint.ts')).toEqual([]);
  });

  it('allows a magic number in a test file', async () => {
    expect(await ruleIds('export const x: number = 42;\n', 'src/vitest.test.ts')).toEqual([]);
  });
});
