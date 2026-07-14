// Setup for the `a11y` browser project. Intentionally does NOT import
// `@testing-library/jest-dom` — that package references a global `expect` which
// vitest does not inject in browser mode, causing a "expect is not defined"
// error at setup load. The a11y browser tests only rely on the custom
// `toHaveNoViolations` matcher registered by @/test/a11y.
//
// We also import the global stylesheet (Tailwind/PostCSS, processed by Vite) so
// that axe-core's color-contrast rule evaluates REAL computed colors instead of
// defaulting to black-on-white. Without this, contrast checks are meaningless.
import '@/index.css';
import '@/test/a11y';
