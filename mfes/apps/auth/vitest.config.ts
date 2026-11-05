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
    exclude: ['tests/server/**'],
    coverage: {
      provider: 'v8',
      include: ['app/**/*.tsx', '../../packages/ui/src/**/*.tsx', '../../packages/ui/src/**/*.ts'],
      exclude: ['app/layout.tsx', 'app/page.tsx', '**/*.d.ts'],
    },
  },
});
