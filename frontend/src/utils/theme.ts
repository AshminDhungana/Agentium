const TRANSITION_DURATION_MS = 240;
const STORAGE_KEY = 'theme';

/**
 * Reads the current dark-mode state from the document root.
 */
export function isDarkMode(): boolean {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
}

/**
 * Applies a dark/light theme in a single coordinated step and opens a short
 * "theme-transition" window on <html> so every themed property (backgrounds,
 * borders, text, icons, shadows) animates with identical timing.
 *
 * Without that window, Tailwind `dark:` utilities and the `--c-*` CSS variables
 * flip instantly while only elements with an explicit `transition-*` class
 * animate — producing a janky, out-of-sync switch. The window closes after the
 * transition so normal interactions (hover/focus) keep their own transitions.
 */
export function setDarkMode(next: boolean): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  root.classList.add('theme-transition');
  root.classList.toggle('dark', next);

  try {
    localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light');
  } catch {
    /* storage can be unavailable (private mode); theme still applies in-session */
  }

  window.dispatchEvent(new Event('agentium:theme-change'));

  window.clearTimeout((setDarkMode as unknown as { _t?: number })._t);
  (setDarkMode as unknown as { _t?: number })._t = window.setTimeout(() => {
    root.classList.remove('theme-transition');
  }, TRANSITION_DURATION_MS);
}

/**
 * Toggles between light and dark mode.
 */
export function toggleTheme(): void {
  setDarkMode(!isDarkMode());
}
