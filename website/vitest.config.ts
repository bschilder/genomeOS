import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    exclude: ['tests/site.spec.ts', '**/node_modules/**', '**/.git/**'],
    fileParallelism: false,
    globalSetup: ['./tests/setup/build.ts'],
  },
});
