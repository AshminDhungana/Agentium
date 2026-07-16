# Auth Card Polish — Design Spec

**Date:** 2026-07-16
**Status:** Approved
**Scope:** Frontend only — `LoginPage.tsx`, `SignupPage.tsx`, and a new shared `AuthCard` component.
**Out of scope:** `AuthLayout` (shield theme toggle) and `FlatMapAuthBackground` (animated map). These are preserved exactly as-is.

## Goal

Apply a *subtle polish* to the login and signup card UI without changing behavior, color identity, or the surrounding background/animation. The blue (`blue-600`) accent is retained as the sole primary accent. A shared `AuthCard` shell is extracted so the two pages share identical, maintainable markup.

## Constraints (fixed, do not change)

- Background + Three.js animated world map (`FlatMapAuthBackground`) — unchanged.
- Shield logo in `AuthLayout` remains the light/dark mode switch — unchanged.
- Primary accent color stays `blue-600` (no gold/bronze shift).
- All existing functionality: `useAuthStore` login/signup, client-side validation, error banners, success redirect, password visibility toggles, password-match feedback.
- All existing `aria-*` attributes, `role="alert"` regions, labels, and keyboard behavior.

## 1. Architecture

- **New file:** `frontend/src/components/auth/AuthCard.tsx`
  - Owns the card shell: outer container (`bg-white dark:bg-[#161b27] rounded-2xl shadow-xl border ... backdrop-blur p-8`), a header region (renders `title` + `subtitle` props), a content slot (`children`), a footer slot (optional `footer` prop), and the fixed "Intelligence requires governance" tagline.
  - Props: `{ title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }`.
  - No business logic, no store imports.
- **`LoginPage.tsx`** becomes a thin consumer: renders the form inside `<AuthCard title="Welcome Back" subtitle="Sign in to manage your AI governance system">`, passing the "Don't have an account? Request Access" block as `footer`.
- **`SignupPage.tsx`** becomes a thin consumer: renders the form inside `<AuthCard title="Create Account" subtitle="Request access to the governance system">`, passing the "Already have an account? Sign In" block as `footer`. The success state remains a separate card rendered outside `AuthCard` (as today).
- `AuthLayout` (`App.tsx`) and `FlatMapAuthBackground` are not modified.

## 2. Visual Refinements (subtle, blue kept)

Card shell:
- Retain `bg-white dark:bg-[#161b27]`, `rounded-2xl`, `shadow-xl`, and the existing border (`border-gray-200 dark:border-[#1e2535]`).
- Slightly stronger `backdrop-blur` (e.g. `backdrop-blur-md`) and a subtle gradient hairline top edge for depth (a thin `border-t` or pseudo accent using blue at low opacity — no new color identity).
- Keep `p-8`; tighten internal vertical gaps to a consistent 8pt rhythm.

Header:
- Same copy. Apply slightly tighter letter-spacing on the title (`tracking-tight`) and marginally improved subtitle contrast in light mode (`text-gray-600` → `text-gray-500` is not required; keep readable ≥4.5:1).

Inputs:
- Add subtle leading icons inside the existing `relative` wrappers (lucide `User`, `Lock`, `Mail`) positioned left, with input `padding-left` adjusted so text does not overlap. Icons use muted gray, consistent with current focus/placeholder tones.
- Preserve the blue focus ring (`focus:ring-2 focus:ring-blue-500 focus:border-blue-500`) and the show/hide password toggle button (position unchanged on the right).
- No color change to borders, backgrounds, or text.

Button:
- Keep `bg-blue-600 hover:bg-blue-700` and the existing `hover:scale-[1.02] active:scale-[0.98]` transition.
- Add a small trailing arrow icon (`lucide ArrowRight`) as a subtle motion cue; loading state (spinner + label) unchanged.

Footer + tagline:
- Keep the blue link; refine the top divider (`border-t`) to match the shell border.
- Style the "Intelligence requires governance" tagline with letter-spacing (`tracking-wide`) and a muted tone. No emoji, no gold.

Accessibility:
- Add `motion-reduce:transition-none` and `motion-reduce:transform-none` to hover/scale effects (button + shield already handled in `AuthLayout`, but ensure new card hover/scale respect reduced motion).
- Preserve all existing `aria-describedby`, `aria-invalid`, and `role="alert"` wiring.

## 3. Behavior, Data, Error Handling

Unchanged from current implementation:
- `useAuthStore().login(username, password)` and `useAuthStore().signup(username, email, password)` calls.
- Client-side validation (username length, password length, match) and inline error banner.
- Success path: signup shows the success card and redirects to `/login` after 3s; login navigates to `/` on success.
- Password visibility toggles and real-time password-match feedback retained.

## 4. Testing

- Reuse existing a11y browser tests in `*.a11y.browser.test.tsx`. `LoginPage`/`SignupPage` do not currently have dedicated a11y tests; add one `AuthCard.a11y.browser.test.tsx` smoke test (renders `<AuthCard>` with sample children, audits light + dark via `auditRoute`) to lock in no-regression coverage for the new shared component.
- Verify both light and dark themes pass axe (no new contrast violations from leading icons or the arrow).
- Confirm no duplicate `id` attributes (e.g., `login-error` / `signup-error`) across the two pages.
- Manual: toggle theme via shield; confirm card, inputs, button, and tagline render correctly in both themes; confirm reduced-motion disables scale transforms.

## 5. Acceptance Criteria

- [ ] `AuthCard` component exists and is used by both pages.
- [ ] Login and signup render visually identical card structure (header, footer, tagline).
- [ ] Blue accent unchanged; no gold introduced.
- [ ] Shield toggle and map background unaffected.
- [ ] Leading input icons + trailing button arrow present, with no contrast/overlap issues.
- [ ] Reduced-motion respected on card hover/scale.
- [ ] No a11y regressions; existing behavior intact.
