/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { playwright } from '@vitest/browser-playwright';
const dirname = typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url));

// More info at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    },
    dedupe: ['react', 'react-dom']
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      }
    }
  },
  build: {
    target: 'esnext',
    sourcemap: true
  },
  test: {
    projects: [{
      // Component unit tests (jsdom). Scoped to src/components/{chat,tasks}
      // so it never disturbs the other suites (notably the storybook/browser
      // project). extends: true pulls in the root resolve.alias ('@' -> ./src)
      // and react() plugin.
      extends: true,
      test: {
        name: 'unit',
        environment: 'jsdom',
        globals: true,
        setupFiles: ['./src/test/setup.ts'],
        include: [
          'src/components/chat/**/*.test.{ts,tsx}',
          'src/components/tasks/**/*.test.{ts,tsx}',
          'src/components/models/**/*.test.{ts,tsx}',
          'src/components/dashboard/**/*.test.{ts,tsx}',
          'src/components/layout/**/*.test.{ts,tsx}',
          'src/components/ui/**/*.test.{ts,tsx}',
          'src/pages/**/*.test.{ts,tsx}',
          'src/store/**/*.test.{ts,tsx}',
          'src/**/*.a11y.test.{ts,tsx}',
        ],
      },
    }, {
      extends: true,
      plugins: [
      // The plugin will run tests for the stories defined in your Storybook config
      // See options at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon#storybooktest
      storybookTest({
        configDir: path.join(dirname, '.storybook')
      })],
      test: {
        name: 'storybook',
        browser: {
          enabled: true,
          headless: true,
          provider: playwright({}),
          instances: [{
            browser: 'chromium'
          }]
        }
      }
    }, {
      // Accessibility audit project: runs axe-core against a REAL Chromium
      // layout so the `color-contrast` rule (which needs layout/getComputedStyle)
      // is meaningful. Structural rules (names, roles, labels) are also covered
      // here in both light and dark themes.
      extends: true,
      test: {
        name: 'a11y',
        include: ['src/**/*.a11y.browser.test.{ts,tsx}'],
        globals: true,
        setupFiles: ['./src/test/setup.a11y.ts'],
        browser: {
          enabled: true,
          headless: true,
          provider: playwright({}),
          instances: [{
            browser: 'chromium'
          }]
        }
      }
    }]
  }
});