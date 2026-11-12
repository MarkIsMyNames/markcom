import { createEslintConfig } from './src/eslint.ts';

export default createEslintConfig({ tsconfigRootDir: import.meta.dirname });
