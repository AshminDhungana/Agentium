import React, { useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useFocusTrap } from './useFocusTrap';

type ModalSize = 'sm' | 'md' | 'lg' | 'xl';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: ModalSize;
  /** Hide the default header close (X) button. */
  hideClose?: boolean;
  /** Disable closing when the backdrop is clicked. */
  disableBackdropClose?: boolean;
  className?: string;
}

const SIZE_CLASSES: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

/**
 * Accessible modal dialog: portaled to <body>, aria-modal + role="dialog",
 * focus trap with focus restore (see useFocusTrap), Escape-to-close, and
 * backdrop click-to-close. Replaces ad-hoc fixed-overlay dialogs across the
 * app so keyboard and screen-reader users get a consistent experience.
 */
export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  hideClose = false,
  disableBackdropClose = false,
  className = '',
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, open, onClose);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !disableBackdropClose) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        aria-labelledby={typeof title === 'string' ? undefined : title ? 'modal-title' : undefined}
        aria-describedby={description ? 'modal-description' : undefined}
        tabIndex={-1}
        className={`w-full ${SIZE_CLASSES[size]} max-h-[90vh] overflow-hidden flex flex-col
          bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]
          shadow-2xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)]
          focus:outline-none`}
      >
        {(title || !hideClose) && (
          <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200 dark:border-[#1e2535]">
            <div className="min-w-0">
              {title &&
                (typeof title === 'string' ? (
                  <h2 id="modal-title" className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                    {title}
                  </h2>
                ) : (
                  <div id="modal-title">{title}</div>
                ))}
              {description && (
                <p id="modal-description" className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  {description}
                </p>
              )}
            </div>
            {!hideClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close dialog"
                className="shrink-0 p-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer && (
          <div className="px-5 py-4 border-t border-gray-200 dark:border-[#1e2535] flex items-center justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};

Modal.displayName = 'Modal';
