import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface WidgetCardProps {
  title: string;
  icon: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  'aria-label'?: string;
}

export function WidgetCard({
  title,
  icon: Icon,
  action,
  children,
  className = '',
  contentClassName = '',
  ...rest
}: WidgetCardProps) {
  return (
    <section
      aria-label={rest['aria-label'] ?? title}
      className={`flex flex-col rounded-xl border border-hairline bg-panel shadow-sm transition-colors duration-200 ${className}`}
    >
      <header className="flex items-center gap-3 border-b border-hairline px-5 py-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <h2 className="flex-1 text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
        {action}
      </header>
      <div className={`flex-1 ${contentClassName}`}>{children}</div>
    </section>
  );
}
