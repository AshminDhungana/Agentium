import React, {  useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useFocusTrap } from '../../hooks/useFocusTrap';

/**
 * @description A slide-over panel that slides in from the right side of the screen.
 * Includes focus trapping, ESC key to close, and body scroll lock when open.
 * @example
 * ```tsx
 * import { SlideOver } from '@/components/ui/SlideOver';
 *
 * <SlideOver
 *   isOpen={isOpen}
 *   onClose={close}
 *   title="Agent Details"
 *   icon={InfoIcon}
 * >
 *   <AgentDetailContent />
 * </SlideOver>
 * ```
 * @param {boolean} props.isOpen - Whether the slide-over is visible.
 * @param {() => void} props.onClose - Callback fired when the panel should close.
 * @param {React.ReactNode} props.title - Header title content.
 * @param {React.ElementType} [props.icon] - Optional icon component to display in the header.
 * @param {React.ReactNode} props.children - Content rendered inside the panel.
 * @param {React.ReactNode} [props.subtitle] - Optional subtitle shown below the title.
 */

interface SlideOverProps {
    isOpen: boolean;
    onClose: () => void;
    title: React.ReactNode;
    icon?: React.ElementType;
    children: React.ReactNode;
    subtitle?: React.ReactNode;
}

export const SlideOver: React.FC<SlideOverProps> = ({
    isOpen,
    onClose,
    title,
    icon: Icon,
    children,
    subtitle
}) => {
    const containerRef = useRef<HTMLDivElement>(null);
    useFocusTrap(containerRef, isOpen);

    // Prevent body scroll when open
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'unset';
        }
        return () => {
            document.body.style.overflow = 'unset';
        };
    }, [isOpen]);

    // Handle escape key
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        if (isOpen) {
            window.addEventListener('keydown', handleEscape);
        }
        return () => {
            window.removeEventListener('keydown', handleEscape);
        };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex justify-end" ref={containerRef}>
            {/* Backdrop */}
            <div 
                className="absolute inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm transition-opacity"
                onClick={onClose}
                aria-hidden="true"
            />

            {/* SlideOver Panel */}
            <div 
                className="relative w-full max-w-2xl bg-white dark:bg-[#161b27] shadow-2xl dark:shadow-[0_0_40px_rgba(0,0,0,0.5)] 
                flex flex-col h-full transform transition-transform duration-300 ease-in-out border-l border-gray-200 dark:border-[#1e2535] 
                animate-in slide-in-from-right"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-[#1e2535] bg-gray-50/50 dark:bg-[#0f1117]/50 flex-shrink-0">
                    <div className="flex items-center gap-3 min-w-0">
                        {Icon && (
                            <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                                <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                        )}
                        <div className="min-w-0">
                            <h2 className="text-lg font-bold text-gray-900 dark:text-white truncate">
                                {title}
                            </h2>
                            {subtitle && (
                                <p className="text-xs text-gray-600 dark:text-gray-400 truncate mt-0.5">
                                    {subtitle}
                                </p>
                            )}
                        </div>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 ml-4 flex-shrink-0 rounded-lg text-gray-600 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                        aria-label="Close panel"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto">
                    {children}
                </div>
            </div>
        </div>
    );
};
