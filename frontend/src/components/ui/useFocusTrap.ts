import { useEffect, useRef } from 'react';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * Traps focus within `ref` while `active`, moves initial focus into the
 * container, closes on Escape, and restores focus to the previously focused
 * element on deactivation (focus restore). Used by the Modal primitive.
 */
export function useFocusTrap(
  ref: React.RefObject<HTMLElement>,
  active: boolean,
  onClose?: () => void
) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!active || !ref.current) return;
    const container = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const getFocusable = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        // In real browsers an off-screen/hidden element has a null offsetParent;
        // jsdom never computes layout so offsetParent is always null — treat
        // non-disabled, attached elements as focusable there.
        (el) => !el.hasAttribute('disabled') && (el.offsetParent !== null || document.body.contains(el))
      );

    // Move focus into the dialog (prefer the first focusable element).
    const focusable = getFocusable();
    (focusable[0] ?? container).focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current?.();
        return;
      }
      if (e.key !== 'Tab') return;

      const items = getFocusable();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;

      if (e.shiftKey && activeEl === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && activeEl === last) {
        e.preventDefault();
        first.focus();
      }
    };

    container.addEventListener('keydown', onKeyDown);
    return () => {
      container.removeEventListener('keydown', onKeyDown);
      // Restore focus to the element that opened the dialog.
      previouslyFocused?.focus?.();
    };
  }, [active, ref]);
}
