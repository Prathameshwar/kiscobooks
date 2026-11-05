import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Test against @janso/ui source, the same way Next transpiles it.
    alias: { '@janso/ui': resolve(__dirname, '../../packages/ui/src/index.ts') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.tsx'],
    css: false, // components style via class names; CSS is not under test here
    include: ['tests/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      /*
       * This app's own files only. `@janso/ui` is covered by its own suite with its own
       * thresholds; counting its source here double-counts the library and flatters the
       * console's number — a few hundred well-tested library lines would hide an untested
       * screen.
       */
      include: ['app/**/*.ts', 'app/**/*.tsx'],
      // `layout.tsx` is the document shell (no branches, nothing to assert without an E2E
      // browser); `page.tsx` is an async Server Component, which RTL cannot mount.
      exclude: ['app/layout.tsx', 'app/page.tsx', '**/*.d.ts'],
      // Matches the floor @janso/ui holds itself to, so the app cannot be the weak link.
      thresholds: { lines: 90, functions: 90, statements: 90, branches: 85 },
    },
  },
});
