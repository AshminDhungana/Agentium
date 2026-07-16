import type { RefObject } from 'react';
import { Menu, PanelLeftClose, PanelLeftOpen, Sun, Moon } from 'lucide-react';

interface TopBarProps {
  title: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenMobile: () => void;
  hamburgerRef?: RefObject<HTMLButtonElement>;
}

export function TopBar({ title, collapsed, onToggleCollapse, onOpenMobile, hamburgerRef }: TopBarProps) {
  const isDark =
    typeof window !== 'undefined' && document.documentElement.classList.contains('dark');

  const toggleTheme = () => {
    const next = !isDark;
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    window.dispatchEvent(new Event('agentium:theme-change'));
  };

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-2 border-b border-gray-200 bg-white px-4 dark:border-[#1e2535] dark:bg-[#161b27]">
      <button
        ref={hamburgerRef}
        onClick={onOpenMobile}
        aria-label="Open navigation menu"
        className="rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5 lg:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <button
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-pressed={collapsed}
        className="hidden rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5 lg:inline-flex"
      >
        {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
      </button>

      <h1 className="truncate text-base font-semibold text-gray-900 dark:text-white">{title}</h1>

      <div className="ml-auto">
        <button
          onClick={toggleTheme}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5"
        >
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </div>
    </header>
  );
}
