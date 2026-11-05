import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { environment: 'node',
  setupFiles: ['./tests/server/setup.ts'], include: ['tests/server/**/*.test.ts'] } });
