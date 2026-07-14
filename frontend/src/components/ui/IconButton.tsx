import { ButtonHTMLAttributes, forwardRef } from 'react';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  // Required: every icon-only button must provide an accessible name.
  'aria-label': string;
}

// Accessible icon button: requires an aria-label, renders a visible
// focus ring, and forwards refs. Use this for every icon-only action so
// screen-reader and keyboard users get a discernible name + focus indicator.
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className = '', children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      className={
        'inline-flex items-center justify-center rounded-lg p-2 text-gray-700 ' +
        'dark:text-gray-300 transition-colors hover:bg-gray-100 dark:hover:bg-white/10 ' +
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 ' +
        'dark:focus-visible:ring-offset-[#161b27] disabled:opacity-50 ' +
        className
      }
      {...props}
    >
      {children}
    </button>
  )
);
IconButton.displayName = 'IconButton';
