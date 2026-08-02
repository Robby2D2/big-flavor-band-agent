import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The project's first automated frontend tests (see .agents/TESTING.md). Scoped
// to component/hook unit tests under __tests__/ — Next's own routing, the BFF
// route handlers, and anything needing a real browser stay out of scope and are
// still covered by `npm run lint` + `npm run build`.
//
// `.mts` (not `.ts`) so Vite loads it as ESM natively; `resolve.tsconfigPaths`
// picks up the `@/*` alias from tsconfig.json without a plugin.
export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/__tests__/**/*.test.{ts,tsx}'],
    exclude: ['node_modules/**', '.next/**'],
  },
});
