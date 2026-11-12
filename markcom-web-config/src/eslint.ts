import js from '@eslint/js';
import eslintReact from '@eslint-react/eslint-plugin';
import prettierConfig from 'eslint-config-prettier';
import i18next from 'eslint-plugin-i18next';
import jsxA11y from 'eslint-plugin-jsx-a11y-x';
import reactHooks from 'eslint-plugin-react-hooks';
import security from 'eslint-plugin-security';
import noUnneededEffects from 'eslint-plugin-react-you-might-not-need-an-effect';
import sonarjs from 'eslint-plugin-sonarjs';
import storybook from 'eslint-plugin-storybook';
import type { Linter } from 'eslint';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export type EslintOptions = {
  /** The folder holding the site's tsconfig.json: pass `import.meta.dirname`. */
  tsconfigRootDir: string;
};

/** Some plugins' published types clash with exactOptionalPropertyTypes; check their shape instead. */
function isFlatConfig(value: unknown): value is Linter.Config {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toFlatConfigs(value: unknown, name: string): Linter.Config[] {
  const configs: unknown[] = Array.isArray(value) ? value : [value];
  if (!configs.every(isFlatConfig)) {
    throw new Error(`${name} is not a flat config`);
  }
  return configs;
}

const SOURCE: string[] = ['**/*.{ts,tsx}'];
const TESTS: string[] = [
  '**/*.test.{ts,tsx}',
  '**/*.stories.tsx',
  'e2e/**',
  'visual/**',
  'src/setupTests.ts',
];
/** The only files allowed raw values: they are where the named values are defined. */
const VALUE_HOMES: string[] = ['src/config.ts', 'src/styles/tokens.ts', '*.config.ts'];
const IGNORED: string[] = [
  'build',
  'dist',
  'coverage',
  'storybook-static',
  'playwright-report',
  'test-results',
  '!.storybook',
];
/** Text-bearing JSX attributes that must come from the locale files. */
const TEXT_ATTRIBUTES: string[] = [
  'aria-label',
  'aria-description',
  'alt',
  'title',
  'placeholder',
  'label',
];

/** House rule: every variable, class field and parameter carries a type annotation. */
type RestrictedSyntax = { selector: string; message: string };
const ANNOTATIONS: RestrictedSyntax[] = [
  {
    selector:
      'VariableDeclarator[id.typeAnnotation=undefined]:not(ForOfStatement > VariableDeclaration > VariableDeclarator, ForInStatement > VariableDeclaration > VariableDeclarator)',
    message: 'Annotate the variable type.',
  },
  {
    selector: 'PropertyDefinition[typeAnnotation=undefined]',
    message: 'Annotate the field type.',
  },
  {
    selector:
      ':function > :matches(Identifier, ObjectPattern, ArrayPattern, RestElement).params[typeAnnotation=undefined]',
    message: 'Annotate the parameter type.',
  },
];
const RAW_VALUES: RestrictedSyntax[] = [
  {
    selector: String.raw`Literal[value=/^https?:\/\//]`,
    message: 'Put URLs and paths in src/config.ts.',
  },
  {
    selector: String.raw`Literal[value=/#[0-9a-fA-F]{3,8}\b/]`,
    message: 'Colours live in src/styles/tokens.ts; use theme.color.* in styles.',
  },
  {
    selector: String.raw`Literal[value=/^-?\d*\.?\d+(px|rem|em|vh|vw|dvh|svh|ms|s|%)$/]`,
    message: 'Sizes, spacing and durations live in src/styles/tokens.ts; use theme.*.',
  },
  {
    selector: String.raw`Literal[value=/(^|\s)-?\d*\.?\d+(px|rem|em|ms)(\s|$)/]`,
    message: 'Sizes, spacing and durations live in src/styles/tokens.ts; use theme.*.',
  },
  {
    selector: 'TSNeverKeyword',
    message: 'Do not write never; model the impossible case with a narrower type.',
  },
  {
    selector: 'CallExpression[callee.name="useEffect"] > ArrowFunctionExpression[async=true]',
    message: 'Never fetch or run async work in an effect: it belongs in a ViewModel command.',
  },
];

const HOUSE_RULES: Linter.RulesRecord = {
  'no-console': 'error',
  'no-debugger': 'error',
  eqeqeq: ['error', 'always'],
  curly: ['error', 'all'],
  'no-nested-ternary': 'error',
  'no-else-return': 'error',
  'prefer-template': 'error',
  'object-shorthand': 'error',
  'prefer-destructuring': ['error', { array: false, object: true }],
  '@typescript-eslint/consistent-type-imports': 'error',
  '@typescript-eslint/consistent-type-exports': 'error',
  '@typescript-eslint/switch-exhaustiveness-check': 'error',
  // House rule: the variable's annotation carries the type arguments, not the constructor call.
  '@typescript-eslint/consistent-generic-constructors': ['error', 'type-annotation'],
  // House rule: interface for contracts a class implements (and module augmentation), type for data.
  '@typescript-eslint/consistent-type-definitions': 'off',
  // House rule: every variable and parameter is annotated, even when the type could be inferred.
  '@typescript-eslint/no-inferrable-types': 'off',
  '@typescript-eslint/naming-convention': [
    'error',
    { selector: 'variable', format: ['camelCase', 'PascalCase', 'UPPER_CASE'] },
    { selector: 'function', format: ['camelCase', 'PascalCase'] },
    { selector: 'typeLike', format: ['PascalCase'] },
  ],
  'react-hooks/exhaustive-deps': 'error',
  '@typescript-eslint/no-restricted-types': [
    'error',
    {
      types: {
        object: 'Use a specific type.',
        Object: 'Use a specific type.',
        '{}': 'Use a specific type.',
        Function: 'Use a specific function signature.',
      },
    },
  ],
  'i18next/no-literal-string': [
    'error',
    {
      mode: 'jsx-only',
      'jsx-attributes': { include: TEXT_ATTRIBUTES },
      // Strings with no letters (punctuation, numbers) are allowed; anything with a letter is text.
      words: { exclude: ['^[^a-zA-Z\u00C0-\u024F]*$'] },
    },
  ],
  '@typescript-eslint/no-magic-numbers': [
    'error',
    { ignore: [-1, 0, 1], ignoreEnums: true, ignoreReadonlyClassProperties: true },
  ],
  '@typescript-eslint/explicit-function-return-type': [
    'error',
    {
      allowExpressions: false,
      allowTypedFunctionExpressions: false,
      allowHigherOrderFunctions: false,
      allowDirectConstAssertionInArrowFunctions: false,
      allowConciseArrowFunctionExpressionsStartingWithVoid: false,
      allowFunctionsWithoutTypeParameters: false,
      allowIIFEs: false,
    },
  ],
  'no-restricted-syntax': ['error', ...ANNOTATIONS, ...RAW_VALUES],
};

/** The house ESLint config every react-ui site and web library uses, strictest settings on. */
export function createEslintConfig(options: EslintOptions): Linter.Config[] {
  return defineConfig(
    globalIgnores(IGNORED),
    {
      files: SOURCE,
      extends: [
        js.configs.recommended,
        tseslint.configs.strictTypeChecked,
        tseslint.configs.stylisticTypeChecked,
        eslintReact.configs['strict-type-checked'],
        reactHooks.configs.flat['recommended-latest'],
        noUnneededEffects.configs.strict,
        jsxA11y.configs.strict,
        ...toFlatConfigs(sonarjs.configs?.['recommended'], 'sonarjs recommended'),
        ...toFlatConfigs(security.configs.recommended, 'security recommended'),
        i18next.configs['flat/recommended'],
      ],
      languageOptions: {
        globals: { ...globals.browser, ...globals.node },
        parserOptions: { projectService: true, tsconfigRootDir: options.tsconfigRootDir },
      },
      linterOptions: { reportUnusedDisableDirectives: 'error', noInlineConfig: true },
      rules: HOUSE_RULES,
    },
    {
      files: ['**/*.css.ts'],
      rules: { '@typescript-eslint/no-magic-numbers': 'off' },
    },
    {
      files: VALUE_HOMES,
      rules: {
        '@typescript-eslint/no-magic-numbers': 'off',
        'no-restricted-syntax': ['error', ...ANNOTATIONS],
      },
    },
    {
      files: TESTS,
      rules: {
        '@typescript-eslint/no-magic-numbers': 'off',
        'no-restricted-syntax': 'off',
        '@typescript-eslint/explicit-function-return-type': 'off',
        'i18next/no-literal-string': 'off',
        'sonarjs/no-hardcoded-ip': 'off',
        // Shared suites (describeLocaleSet, describeLanguageRouting) register their tests inside a call.
        'sonarjs/no-empty-test-file': 'off',
      },
    },
    ...toFlatConfigs(storybook.configs['flat/recommended'], 'storybook flat/recommended'),
    prettierConfig,
  );
}
