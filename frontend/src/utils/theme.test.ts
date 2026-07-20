import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isDarkMode, setDarkMode, toggleTheme } from './theme';

const TRANSITION_DURATION_MS = 240;

function fireThemeChange() {
  window.dispatchEvent(new Event('agentium:theme-change'));
}

describe('theme utils', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark', 'theme-transition');
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.documentElement.classList.remove('dark', 'theme-transition');
    localStorage.clear();
  });

  it('setDarkMode(true) enables dark + opens the transition window + persists + notifies', () => {
    const listener = vi.fn();
    window.addEventListener('agentium:theme-change', listener);

    setDarkMode(true);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('theme-transition')).toBe(true);
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(listener).toHaveBeenCalledTimes(1);

    window.removeEventListener('agentium:theme-change', listener);
  });

  it('setDarkMode(false) disables dark mode', () => {
    setDarkMode(true);
    setDarkMode(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(localStorage.getItem('theme')).toBe('light');
  });

  it('closes the transition window after the transition duration', () => {
    setDarkMode(true);
    expect(document.documentElement.classList.contains('theme-transition')).toBe(true);
    vi.advanceTimersByTime(TRANSITION_DURATION_MS + 10);
    expect(document.documentElement.classList.contains('theme-transition')).toBe(false);
  });

  it('toggleTheme flips the current mode', () => {
    expect(isDarkMode()).toBe(false);
    toggleTheme();
    expect(isDarkMode()).toBe(true);
    toggleTheme();
    expect(isDarkMode()).toBe(false);
  });

  it('re-toggling clears the prior close timer (no premature window close)', () => {
    setDarkMode(true);
    vi.advanceTimersByTime(TRANSITION_DURATION_MS + 10); // would close the window
    setDarkMode(false);
    // new window opened for the second toggle
    expect(document.documentElement.classList.contains('theme-transition')).toBe(true);
    expect(isDarkMode()).toBe(false);
    fireThemeChange();
  });
});
