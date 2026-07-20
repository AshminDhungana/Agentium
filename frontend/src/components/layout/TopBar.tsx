import { useEffect, useState, type RefObject } from 'react';
import { Menu, PanelLeftClose, PanelLeftOpen, Sun, Moon } from 'lucide-react';
import { isDarkMode, setDarkMode } from '../../utils/theme';

interface TopBarProps {
  title: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenMobile: () => void;
  hamburgerRef?: RefObject<HTMLButtonElement>;
}

export function TopBar({ title, collapsed, onToggleCollapse, onOpenMobile, hamburgerRef }: TopBarProps) {
  const [isDark, setIsDark] = useState(() => isDarkMode());

  // Keep the toggle in sync with the actual theme, including changes made
  // elsewhere (e.g. the auth-layout toggle) or restored from localStorage.
  useEffect(() => {
    const sync = () =>
      setIsDark(document.documentElement.classList.contains('dark'));
    window.addEventListener('agentium:theme-change', sync);
    return () => window.removeEventListener('agentium:theme-change', sync);
  }, []);

  const toggleTheme = () => {
    const next = !isDark;
    setDarkMode(next);
    setIsDark(next);
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
          className="relative rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5"
        >
          <Sun
            className={`absolute inset-0 m-auto h-5 w-5 transition-all duration-300 ease-out ${
              isDark ? 'rotate-0 scale-100 opacity-100' : 'rotate-90 scale-0 opacity-0'
            }`}
          />
          <Moon
            className={`h-5 w-5 transition-all duration-300 ease-out ${
              isDark ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100'
            }`}
          />
        </button>
      </div>
    </header>
  );
}
