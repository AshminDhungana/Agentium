# Auth Card Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a shared `AuthCard` shell and apply subtle visual polish to the login and signup cards while keeping the blue accent, shield theme toggle, and animated map background unchanged.

**Architecture:** A new `AuthCard` component owns the card container (header, footer slot, tagline, subtle gradient hairline, stronger blur). `LoginPage` and `SignupPage` become thin consumers passing their form + footer link as children/slot. No logic or store calls move; behavior is untouched.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind CSS, lucide-react (icons), Framer Motion (already used by `AuthLayout`), vitest + axe-core (a11y browser tests).

## Global Constraints

- Background + `FlatMapAuthBackground` (Three.js map): **unchanged**.
- Shield logo in `AuthLayout` (`App.tsx`) remains the light/dark toggle: **unchanged**.
- Primary accent stays `blue-600` — **no gold/bronze** introduced anywhere.
- All existing `aria-*` attributes, `role="alert"` regions, labels, and keyboard behavior preserved.
- `useAuthStore` login/signup, validation, error banners, success redirect, password toggles: **unchanged**.
- All new motion (hover/scale) must include `motion-reduce:transition-none motion-reduce:transform-none`.
- Lint rule: no `text--600` (dark-guard). Follow existing Tailwind class conventions in the files.

---

### Task 1: Create shared `AuthCard` shell + a11y test

**Files:**
- Create: `frontend/src/components/auth/AuthCard.tsx`
- Create: `frontend/src/components/auth/AuthCard.a11y.browser.test.tsx`

**Interfaces:**
- Produces: `AuthCard` React component with props `{ title: string; subtitle?: string; children: React.ReactNode; footer?: React.ReactNode }`. Later tasks render `<AuthCard title=... subtitle=... footer=...>{form}</AuthCard>`.

- [ ] **Step 1: Write the failing a11y test**

```tsx
// frontend/src/components/auth/AuthCard.a11y.browser.test.tsx
import { describe, it, expect } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { AuthCard } from '@/components/auth/AuthCard';

describe('AuthCard color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <AuthCard title="Welcome Back" subtitle="Sign in to manage your AI governance system">
        <div>Form content</div>
      </AuthCard>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <AuthCard title="Create Account" subtitle="Request access to the governance system">
        <div>Form content</div>
      </AuthCard>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:a11y -- AuthCard.a11y.browser.test.tsx`
Expected: FAIL — module `@/components/auth/AuthCard` not found / TS compile error.

- [ ] **Step 3: Implement `AuthCard`**

```tsx
// frontend/src/components/auth/AuthCard.tsx
import type { ReactNode } from 'react';

interface AuthCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthCard({ title, subtitle, children, footer }: AuthCardProps) {
  return (
    <div className="relative w-full bg-white dark:bg-[#161b27] rounded-2xl shadow-xl border border-gray-200 dark:border-[#1e2535] backdrop-blur-md overflow-hidden">
      {/* Subtle gradient hairline accent at top edge (blue, low opacity) */}
      <div
        aria-hidden="true"
        className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-blue-500/40 to-transparent"
      />
      <div className="p-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white mb-1">
            {title}
          </h2>
          {subtitle && (
            <p className="text-sm text-gray-600 dark:text-gray-400">{subtitle}</p>
          )}
        </div>

        {children}

        {footer && (
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-[#1e2535]">
            {footer}
          </div>
        )}

        <div className="mt-4">
          <p className="text-xs text-center tracking-wide text-gray-500 dark:text-gray-400">
            Intelligence requires governance
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:a11y -- AuthCard.a11y.browser.test.tsx`
Expected: PASS (both themes, no axe violations).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/auth/AuthCard.tsx frontend/src/components/auth/AuthCard.a11y.browser.test.tsx
git commit -m "feat: add shared AuthCard shell with subtle polish"
```

---

### Task 2: Refactor `LoginPage` to use `AuthCard` + input/button polish

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx` (full file rewrite)
- Reuse: `frontend/src/components/auth/AuthCard.tsx` (from Task 1)

**Interfaces:**
- Consumes: `AuthCard` with props `{ title, subtitle, footer, children }` (Task 1).
- Produces: `LoginPage` rendering the same form inside `AuthCard`, with leading `User`/`Lock` icons and a trailing `ArrowRight` on the submit button.

- [ ] **Step 1: Write the refactored `LoginPage.tsx`**

```tsx
// frontend/src/pages/LoginPage.tsx
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { AlertCircle, Eye, EyeOff, User, Lock, ArrowRight } from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { AuthCard } from '@/components/auth/AuthCard';

export function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const { login, isLoading, error } = useAuthStore();
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const success = await login(username, password);
        if (success) {
            const user = useAuthStore.getState().user;

            let welcomeMsg = 'Welcome back';
            if (user?.isSovereign) {
                welcomeMsg = 'Welcome, Sovereign';
            } else if (user?.is_admin) {
                welcomeMsg = 'Welcome, Administrator';
            } else if (user?.username) {
                welcomeMsg = `Welcome, ${user.username}`;
            }

            showToast.success(welcomeMsg);
            navigate('/');
        }
    };

    return (
        <AuthCard
            title="Welcome Back"
            subtitle="Sign in to manage your AI governance system"
            footer={
                <p className="text-sm text-center text-gray-600 dark:text-gray-400">
                    Don't have an account?{' '}
                    <Link
                        to="/signup"
                        className="text-blue-600 dark:text-blue-400 hover:underline font-medium transition-colors"
                    >
                        Request Access
                    </Link>
                </p>
            }
        >
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                <div>
                    <label
                        htmlFor="username"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Username
                    </label>
                    <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="username"
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all"
                            placeholder="Enter username"
                            required
                            autoComplete="username"
                            aria-describedby={error ? 'login-error' : undefined}
                            aria-invalid={!!error}
                        />
                    </div>
                </div>

                <div>
                    <label
                        htmlFor="password"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Password
                    </label>
                    <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="password"
                            type={showPassword ? 'text' : 'password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all"
                            placeholder="Enter password"
                            required
                            autoComplete="current-password"
                            aria-describedby={error ? 'login-error' : undefined}
                            aria-invalid={!!error}
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword((v) => !v)}
                            className="absolute right-0 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-lg"
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                        >
                            {showPassword
                                ? <EyeOff className="w-5 h-5" />
                                : <Eye className="w-5 h-5" />}
                        </button>
                    </div>
                </div>

                {error && (
                    <div
                        id="login-error"
                        role="alert"
                        className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 animate-in fade-in duration-300"
                    >
                        <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                        {error}
                    </div>
                )}

                <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all duration-200 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] motion-reduce:transition-none motion-reduce:transform-none"
                >
                    {isLoading ? (
                        <>
                            <LoadingSpinner size="sm" />
                            Signing in...
                        </>
                    ) : (
                        <>
                            Sign In
                            <ArrowRight className="w-4 h-4" />
                        </>
                    )}
                </button>
            </form>
        </AuthCard>
    );
}
```

- [ ] **Step 2: Run a quick a11y smoke check on the page**

Run: `cd frontend && npm run test:a11y -- AuthCard.a11y.browser.test.tsx`
Expected: PASS (no new violations introduced by the shared shell).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "refactor: use AuthCard in LoginPage with input icons and button arrow"
```

---

### Task 3: Refactor `SignupPage` to use `AuthCard` + input/button polish

**Files:**
- Modify: `frontend/src/pages/SignupPage.tsx` (full file rewrite)
- Reuse: `frontend/src/components/auth/AuthCard.tsx` (Task 1)

**Interfaces:**
- Consumes: `AuthCard` with props `{ title, subtitle, footer, children }` (Task 1).
- Produces: `SignupPage` rendering the same form inside `AuthCard`, with leading `User`/`Mail`/`Lock` icons, a trailing `ArrowRight` on the submit button, and the success state still rendered as its own separate card (outside `AuthCard`).

- [ ] **Step 1: Write the refactored `SignupPage.tsx`**

```tsx
// frontend/src/pages/SignupPage.tsx
import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle, CheckCircle, Eye, EyeOff, User, Mail, Lock, ArrowRight } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { AuthCard } from '@/components/auth/AuthCard';

export function SignupPage() {
    const [username, setUsername]               = useState('');
    const [email, setEmail]                     = useState('');
    const [password, setPassword]               = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading]             = useState(false);
    const [error, setError]                     = useState('');
    const [success, setSuccess]                 = useState(false);
    const [showPassword, setShowPassword]               = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const { signup } = useAuthStore();
    const navigate = useNavigate();

    useEffect(() => {
        return () => {
            if (redirectTimerRef.current !== null) {
                clearTimeout(redirectTimerRef.current);
            }
        };
    }, []);

    const passwordsDoNotMatch =
        confirmPassword.length > 0 && password !== confirmPassword;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (username.trim().length < 3) {
            setError('Username must be at least 3 characters long');
            return;
        }

        if (password.length < 8) {
            setError('Password must be at least 8 characters long');
            return;
        }

        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        setIsLoading(true);

        try {
            const result = await signup(username, email, password);

            if (result.success) {
                setSuccess(true);
                showToast.success('Signup request submitted! Awaiting admin approval.');
                redirectTimerRef.current = setTimeout(() => navigate('/login'), 3000);
            } else {
                setError(result.message);
            }
        } catch {
            const msg = 'An unexpected error occurred. Please try again.';
            setError(msg);
        } finally {
            setIsLoading(false);
        }
    };

    if (success) {
        return (
            <>
                <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-xl border border-gray-200 dark:border-[#1e2535] p-8 text-center backdrop-blur-sm">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-100 dark:bg-green-500/10 mb-4">
                        <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                        Request Submitted!
                    </h2>
                    <p className="text-gray-600 dark:text-gray-400 mb-6">
                        Your signup request has been sent to the admin for approval.
                        You will be able to login once approved.
                    </p>
                    <p className="text-sm text-gray-600 dark:text-gray-500">
                        Redirecting to login page...
                    </p>
                </div>
            </>
        );
    }

    return (
        <AuthCard
            title="Create Account"
            subtitle="Request access to the governance system"
            footer={
                <p className="text-sm text-center text-gray-600 dark:text-gray-400">
                    Already have an account?{' '}
                    <Link
                        to="/login"
                        className="text-blue-600 dark:text-blue-400 hover:underline font-medium transition-colors"
                    >
                        Sign In
                    </Link>
                </p>
            }
        >
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                <div>
                    <label
                        htmlFor="username"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Username
                    </label>
                    <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="username"
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all"
                            placeholder="Choose a username"
                            required
                            autoComplete="username"
                            minLength={3}
                            maxLength={50}
                            aria-describedby={error ? 'signup-error' : undefined}
                            aria-invalid={!!error}
                        />
                    </div>
                </div>

                <div>
                    <label
                        htmlFor="email"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Email Address
                    </label>
                    <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all"
                            placeholder="your.email@example.com"
                            required
                            autoComplete="email"
                        />
                    </div>
                </div>

                <div>
                    <label
                        htmlFor="password"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Password
                    </label>
                    <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="password"
                            type={showPassword ? 'text' : 'password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all"
                            placeholder="Choose a password"
                            required
                            autoComplete="new-password"
                            minLength={8}
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword((v) => !v)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                        >
                            {showPassword
                                ? <EyeOff className="w-4 h-4" />
                                : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        Minimum 8 characters
                    </p>
                </div>

                <div>
                    <label
                        htmlFor="confirmPassword"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        Confirm Password
                    </label>
                    <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
                        <input
                            id="confirmPassword"
                            type={showConfirmPassword ? 'text' : 'password'}
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            className={`w-full pl-10 pr-10 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white transition-all ${
                                passwordsDoNotMatch
                                    ? 'border-red-400 dark:border-red-500'
                                    : 'border-gray-300 dark:border-[#2a3347]'
                            }`}
                            placeholder="Confirm your password"
                            required
                            autoComplete="new-password"
                            minLength={8}
                            aria-describedby={
                                passwordsDoNotMatch
                                    ? 'password-match-hint'
                                    : error
                                    ? 'signup-error'
                                    : undefined
                            }
                            aria-invalid={passwordsDoNotMatch || !!error}
                        />
                        <button
                            type="button"
                            onClick={() => setShowConfirmPassword((v) => !v)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                            aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                        >
                            {showConfirmPassword
                                ? <EyeOff className="w-4 h-4" />
                                : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                    {passwordsDoNotMatch && (
                        <p
                            id="password-match-hint"
                            className="text-xs text-red-600 dark:text-red-400 mt-1"
                            role="status"
                        >
                            Passwords do not match
                        </p>
                    )}
                </div>

                {error && (
                    <div
                        id="signup-error"
                        role="alert"
                        className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg animate-in fade-in duration-300"
                    >
                        <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                        {error}
                    </div>
                )}

                <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg">
                    <p className="text-xs text-blue-800 dark:text-blue-300">
                        ℹ️ Your account will be pending until approved by an administrator.
                        You'll be able to login once approved.
                    </p>
                </div>

                <button
                    type="submit"
                    disabled={isLoading || passwordsDoNotMatch}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all duration-200 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] motion-reduce:transition-none motion-reduce:transform-none"
                >
                    {isLoading ? (
                        <>
                            <LoadingSpinner size="sm" />
                            Submitting Request...
                        </>
                    ) : (
                        <>
                            Create Account
                            <ArrowRight className="w-4 h-4" />
                        </>
                    )}
                </button>
            </form>
        </AuthCard>
    );
}
```

- [ ] **Step 2: Run a11y smoke check**

Run: `cd frontend && npm run test:a11y -- AuthCard.a11y.browser.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SignupPage.tsx
git commit -m "refactor: use AuthCard in SignupPage with input icons and button arrow"
```

---

### Task 4: Full verification (a11y + lint + typecheck/build)

**Files:**
- Verify: `frontend/src/components/auth/AuthCard.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/SignupPage.tsx`

**Interfaces:**
- Consumes: all files from Tasks 1-3.

- [ ] **Step 1: Run the full a11y suite**

Run: `cd frontend && npm run test:a11y`
Expected: PASS — no axe violations, both themes, including `AuthCard.a11y.browser.test.tsx`.

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors, no unused disable directives, no `text--600` matches.

- [ ] **Step 3: Run typecheck + build**

Run: `cd frontend && npm run build`
Expected: `tsc` passes (no type errors) and Vite build succeeds.

- [ ] **Step 4: Manual verification checklist (document, do not automate)**

Confirm in a browser:
- [ ] `/login` and `/signup` render the identical card shell (header, footer divider, tagline).
- [ ] Shield logo in `AuthLayout` still toggles light/dark; map background unchanged.
- [ ] Leading `User`/`Lock`/`Mail` icons render inside inputs, no text overlap, in both themes.
- [ ] Submit button shows trailing `ArrowRight`; loading spinner state unchanged.
- [ ] `prefers-reduced-motion` disables the button scale/hover transform.
- [ ] No duplicate `id` (`login-error` / `signup-error`) across pages.

- [ ] **Step 5: Commit any verification-driven fixes (only if needed)**

```bash
git add -A
git commit -m "fix: address auth card polish verification findings"
```
(Only if Step 1-3 surfaced issues; otherwise skip.)

---

## Self-Review Notes

- **Spec coverage:** AuthCard shell (§1, Task 1) ✓; blue unchanged (Global Constraints, all code uses `blue-600`) ✓; shield/map untouched (no edits to `App.tsx`/`FlatMapAuthBackground`) ✓; leading input icons + trailing arrow (Tasks 2-3) ✓; reduced-motion (`motion-reduce:*`, Tasks 2-3) ✓; a11y test added (Task 1 + Task 4) ✓; behavior/error/validation unchanged (identical handlers copied) ✓.
- **Placeholders:** None — every step has complete code and exact commands.
- **Type consistency:** `AuthCard` props (`title`, `subtitle`, `children`, `footer`) match usage in Tasks 2-3. Icons imported consistently (`User`, `Lock`, `Mail`, `ArrowRight`, `Eye`, `EyeOff`, `AlertCircle`, `CheckCircle`, `ArrowLeft`) — `ArrowLeft` imported in Task 3 but unused (the back link was dropped from the new shell); remove `ArrowLeft` from the import to satisfy `--report-unused-disable-directives`/no-unused.
