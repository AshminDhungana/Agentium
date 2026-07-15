import { auditRoute } from '@/test/a11yBrowser';

// Positive smoke test for the browser axe harness (color-contrast enabled).
// A properly labelled, AA-contrast component must pass in BOTH light and dark
// themes. The gate's ability to FAIL is exercised by the real component audits
// under src/components/**/*.a11y.browser.test.tsx, so here we only assert the
// happy path stays green.
function CleanComponent() {
  return (
    <div
      data-theme="smoke"
      className="p-4 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white"
    >
      <button
        aria-label="Refresh"
        className="p-1.5 rounded-lg text-blue-600 dark:text-blue-400"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M13 2 3 14h7l-1 8 10-12h-7z" />
        </svg>
      </button>
      <p className="text-gray-600 dark:text-gray-400 mt-2">Secondary helper text</p>
    </div>
  );
}

for (const theme of ['light', 'dark'] as const) {
  test(`clean component has no axe violations (${theme})`, async () => {
    const results = await auditRoute(<CleanComponent />, theme);
    expect(results).toHaveNoViolations();
  });
}
