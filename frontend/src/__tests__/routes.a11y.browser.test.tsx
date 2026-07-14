import { auditRoute } from '@/test/a11yBrowser';

// Baseline accessibility audit (browser + axe-core with color-contrast enabled).
//
// This fixture reproduces the two canonical violation classes found across the
// app during the manual audit:
//   1. an icon-only <button> with only a `title` (no accessible name) — axe
//      flags `button-name`;
//   2. secondary text at `text-gray-400` on a white background — axe flags
//      `color-contrast` in LIGHT theme.
//
// It is intentionally RED until the real components/pages are remediated
// (Tasks 4–12). In Task 12 this fixture is replaced by audits of the actual
// pages (ChatPage, ChannelsPage, etc.) once those fixes land.
function AuditFixture() {
  return (
    <div
      data-theme="fixture"
      className="p-4 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white"
    >
      <button className="p-1.5 rounded-lg text-blue-600">
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M13 2 3 14h7l-1 8 10-12h-7z" />
        </svg>
      </button>
      <p className="text-gray-400 mt-2">Secondary helper text</p>
    </div>
  );
}

for (const theme of ['light', 'dark'] as const) {
  test(`audit fixture has no axe violations (${theme})`, async () => {
    const results = await auditRoute(<AuditFixture />, theme);
    expect(results).toHaveNoViolations();
  });
}
