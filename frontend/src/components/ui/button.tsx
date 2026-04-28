import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "ghost" | "outline";
  size?: "default" | "sm" | "icon";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "default", size = "default", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={`
          inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium
          transition-all duration-200 focus-visible:outline-none focus-visible:ring-2
          focus-visible:ring-indigo-500 focus-visible:ring-offset-2
          focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-900
          disabled:pointer-events-none disabled:opacity-50
          ${variant === "ghost"
            ? "text-gray-700 dark:text-gray-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-gray-900 dark:hover:text-white"
            : variant === "outline"
            ? "border border-slate-200 dark:border-slate-700 bg-transparent text-gray-700 dark:text-gray-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-gray-900 dark:hover:text-white"
            : "bg-slate-900 dark:bg-slate-50 text-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200"
          }
          ${size === "sm"   ? "h-8 px-3 text-xs" :
            size === "icon" ? "h-9 w-9 p-0"      :
                              "h-9 px-4 py-2 text-sm"
          }
          ${className}
        `}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";