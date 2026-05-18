import { useEffect, RefObject } from 'react';

const FOCUSABLE_ELEMENTS_SELECTOR = 
    'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])';

export function useFocusTrap(ref: RefObject<HTMLElement>, isActive: boolean = true) {
    useEffect(() => {
        if (!isActive || !ref.current) return;

        const container = ref.current;
        let focusableElements: HTMLElement[] = [];

        const updateFocusableElements = () => {
            focusableElements = Array.from(
                container.querySelectorAll<HTMLElement>(FOCUSABLE_ELEMENTS_SELECTOR)
            ).filter(el => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true');
        };

        // Initial setup
        updateFocusableElements();

        // Focus the first element initially if none of the elements are focused
        if (focusableElements.length > 0 && !container.contains(document.activeElement)) {
            focusableElements[0].focus();
        }

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key !== 'Tab') return;

            // Re-query in case DOM changed
            updateFocusableElements();

            if (focusableElements.length === 0) {
                e.preventDefault();
                return;
            }

            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];

            if (e.shiftKey) {
                if (document.activeElement === firstElement) {
                    e.preventDefault();
                    lastElement.focus();
                }
            } else {
                if (document.activeElement === lastElement) {
                    e.preventDefault();
                    firstElement.focus();
                }
            }
        };

        container.addEventListener('keydown', handleKeyDown);

        return () => {
            container.removeEventListener('keydown', handleKeyDown);
        };
    }, [ref, isActive]);
}
