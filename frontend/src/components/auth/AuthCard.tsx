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
