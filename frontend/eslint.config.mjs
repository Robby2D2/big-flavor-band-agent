// Flat ESLint config (ESLint 9). Replaces the old .eslintrc.json + `next lint`,
// which Next 16 removed — `next lint` now reads "lint" as a directory and
// errors out, so the script runs the eslint CLI directly instead.
//
// `eslint-config-next` 16 ships flat-config arrays, so its two entry points are
// spread in as-is: core-web-vitals (React, hooks, a11y, the @next/next rules)
// and typescript (typescript-eslint's recommended set).
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

const config = [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'out/**',
      'next-env.d.ts',
      'public/**',
    ],
  },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    rules: {
      // Off, not 'warn': ~100 `any`s exist today, two thirds of them in the
      // app/api/ BFF routes that forward whatever JSON the backend returns,
      // the rest mostly in the produce/audio layer, whose tool params are
      // shaped by the backend registry at runtime rather than in TypeScript.
      // With --max-warnings=0 on the lint script, 'warn' would be an error, so
      // this stays a convention: .agents/CODING.md asks for a real type where
      // one fits, and a reviewer — not this rule — is what enforces it.
      '@typescript-eslint/no-explicit-any': 'off',
      // Unused *arguments* are often there to document a signature; unused
      // locals and imports are real dead code and still error.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { args: 'none', ignoreRestSiblings: true, varsIgnorePattern: '^_' },
      ],
    },
  },
];

export default config;
