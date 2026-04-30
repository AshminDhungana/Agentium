// ─── useToast / showToast ────────────────────────────────────────────────────
// Standardized toast wrapper around react-hot-toast.
//
// • useToast()   — React hook for use inside components
// • showToast    — standalone object for stores, services, and non-component code
//
// All toasts use consistent dark-mode-aware styling and durations:
//   success  → 3 s, green accent
//   error    → 5 s, red accent
//   info     → 4 s, blue accent
// ─────────────────────────────────────────────────────────────────────────────

import toast from 'react-hot-toast';

const TOAST_STYLE = {
    background: '#1f2937',
    color: '#f3f4f6',
    borderRadius: '0.75rem',
    fontSize: '0.875rem',
    padding: '12px 16px',
    border: '1px solid rgba(255,255,255,0.06)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
} as const;

const success = (message: string) =>
    toast.success(message, {
        duration: 3000,
        style: TOAST_STYLE,
        iconTheme: { primary: '#22c55e', secondary: '#fff' },
    });

const error = (message: string) =>
    toast.error(message, {
        duration: 5000,
        style: TOAST_STYLE,
        iconTheme: { primary: '#ef4444', secondary: '#fff' },
    });

const info = (message: string) =>
    toast(message, {
        duration: 4000,
        icon: 'ℹ️',
        style: TOAST_STYLE,
    });

const warning = (message: string) =>
    toast(message, {
        duration: 4000,
        icon: '⚠️',
        style: TOAST_STYLE,
        iconTheme: { primary: '#f59e0b', secondary: '#fff' },
    });

const loading = (message: string) =>
    toast.loading(message, {
        style: TOAST_STYLE,
    });

/**
 * Standalone toast object for non-React contexts (stores, services, utils).
 * Usage: `showToast.success('Saved!')` or `showToast.error('Failed')`
 */
export const showToast = {
    success,
    error,
    info,
    warning,
    loading,
    dismiss: toast.dismiss,
    promise: toast.promise,
} as const;

/**
 * React hook wrapping showToast for component use.
 * Usage: `const toast = useToast(); toast.success('Done!');`
 */
export function useToast() {
    return showToast;
}
