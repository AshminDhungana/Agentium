import { useMemo } from 'react';

export interface PasswordStrengthResult {
    /** 0–100 score */
    strength: number;
    /** Tailwind bg-* class for the progress bar */
    color: string;
    /** Human-readable label: "Weak" | "Moderate" | "Strong" */
    label: string;
    /** Tailwind text-* class for the label */
    textColor: string;
}

/**
 * Derives password strength from a plain-text password string.
 *
 * Scoring:
 *   +25  ≥ 8 characters
 *   +25  ≥ 12 characters
 *   +25  contains both lowercase and uppercase letters
 *   +12.5 contains at least one digit
 *   +12.5 contains at least one special character
 *
 * Thresholds:
 *   < 40  → Weak    (red)
 *   < 70  → Moderate (yellow)
 *   ≥ 70  → Strong  (green)
 *
 * Usage:
 *   const { strength, color, label, textColor } = usePasswordStrength(watchedPassword ?? '');
 */
export function usePasswordStrength(password: string): PasswordStrengthResult {
    const strength = useMemo<number>(() => {
        if (!password) return 0;
        let s = 0;
        if (password.length >= 8)  s += 25;
        if (password.length >= 12) s += 25;
        if (/[a-z]/.test(password) && /[A-Z]/.test(password)) s += 25;
        if (/\d/.test(password))             s += 12.5;
        if (/[^a-zA-Z0-9]/.test(password))  s += 12.5;
        return Math.min(s, 100);
    }, [password]);

    const color =
        strength < 40 ? 'bg-red-500'
        : strength < 70 ? 'bg-yellow-500'
        : 'bg-green-500';

    const label =
        strength < 40 ? 'Weak'
        : strength < 70 ? 'Moderate'
        : 'Strong';

    const textColor =
        strength < 40 ? 'text-red-600 dark:text-red-400'
        : strength < 70 ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-green-600 dark:text-green-400';

    return { strength, color, label, textColor };
}