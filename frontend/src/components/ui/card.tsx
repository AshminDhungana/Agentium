import React from "react";

/**
 * @description A set of composable card sub-components (Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter)
 * for building consistent card-based layouts with dark mode support.
 * @example
 * ```tsx
 * import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
 *
 * <Card>
 *   <CardHeader>
 *     <CardTitle>Card Title</CardTitle>
 *     <CardDescription>Card description text</CardDescription>
 *   </CardHeader>
 *   <CardContent>Content goes here</CardContent>
 * </Card>
 * ```
 * @param {string} [props.className] - Additional CSS classes to merge on each sub-component.
 */
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = "", ...props }, ref) => (
    <div
      ref={ref}
      className={`rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-50 shadow-sm transition-all duration-200 ${className}`}
      {...props}
    />
  )
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = "", ...props }, ref) => (
    <div ref={ref} className={`flex flex-col space-y-1.5 p-6 ${className}`} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className = "", ...props }, ref) => (
    <h3 ref={ref} className={`font-semibold leading-none tracking-tight text-gray-900 dark:text-white ${className}`} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className = "", ...props }, ref) => (
    <p ref={ref} className={`text-sm text-gray-600 dark:text-slate-400 ${className}`} {...props} />
  )
);
CardDescription.displayName = "CardDescription";

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = "", ...props }, ref) => (
    <div ref={ref} className={`p-6 pt-0 ${className}`} {...props} />
  )
);
CardContent.displayName = "CardContent";

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = "", ...props }, ref) => (
    <div ref={ref} className={`flex items-center p-6 pt-0 ${className}`} {...props} />
  )
);
CardFooter.displayName = "CardFooter";