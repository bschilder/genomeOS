import { defineConfig } from 'vitest/config';

export default defineConfig({
  oxc: { jsx: { importSource: 'react', runtime: 'automatic' } },
  test: {
    // Playwright specs are *.spec.ts and must never run under vitest (fast-load design §B.8).
    include: ['tests/**/*.test.ts'],
    fileParallelism: false,
    globalSetup: ['./tests/setup/build.ts'],
  },
});
