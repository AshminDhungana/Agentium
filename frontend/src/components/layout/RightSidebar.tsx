import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import styles from './RightSidebar.module.css';

interface RightSidebarContextValue {
  isCollapsed: boolean;
  toggleCollapse: () => void;
}

const RightSidebarContext = createContext<RightSidebarContextValue | null>(null);

export const useRightSidebar = () => {
  const ctx = useContext(RightSidebarContext);
  if (!ctx) throw new Error('useRightSidebar must be used within RightSidebar');
  return ctx;
};

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  width?: number;
  minWidth?: number;
  position?: 'right' | 'bottom';
  className?: string;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  children,
  width = 320,
  minWidth = 48,
  position = 'right',
  className = '',
}) => {
  const [isMobile, setIsMobile] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const touchStartY = useRef(0);
  const focusableElementsRef = useRef<HTMLElement[]>([]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 767px)');
    const handleChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    setIsMobile(mediaQuery.matches);
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    } else {
      // Fallback for older browsers/jsdom
      mediaQuery.addListener?.(handleChange);
      return () => mediaQuery.removeListener?.(handleChange);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) setIsCollapsed(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !isMobile) return;
    const panel = panelRef.current;
    if (!panel) return;

    focusableElementsRef.current = Array.from(
      panel.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    ).filter(el => !el.hasAttribute('disabled'));

    const firstElement = focusableElementsRef.current[0];
    const lastElement = focusableElementsRef.current[focusableElementsRef.current.length - 1];

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    panel.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keydown', handleEscape);
    firstElement?.focus();

    return () => {
      panel.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isMobile, onClose]);

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.changedTouches?.[0] || e.touches?.[0];
    if (!touch) return;
    touchStartY.current = touch.clientY;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    const touch = e.changedTouches?.[0] || e.touches?.[0];
    if (!touch || !panelRef.current) return;
    const deltaY = touch.clientY - touchStartY.current;
    if (deltaY > 0) {
      panelRef.current.style.transform = `translateY(${deltaY}px)`;
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    const touch = e.changedTouches?.[0];
    if (!touch || !panelRef.current) return;
    panelRef.current.style.transform = '';
    const deltaY = touch.clientY - touchStartY.current;
    if (deltaY > 100) onClose();
  };

  const toggleCollapse = () => setIsCollapsed(prev => !prev);

  if (!isOpen && !isMobile) return null;

  const panelStyle: React.CSSProperties = {
    width: isCollapsed ? minWidth : width,
    transform: isMobile ? 'translateY(100%)' : 'translateX(0)',
  };

  return (
    <RightSidebarContext.Provider value={{ isCollapsed, toggleCollapse }}>
      <div
        data-testid="sidebar-overlay"
        className={`${styles.overlay} ${isOpen ? styles.open : ''} ${isMobile ? styles.mobile : ''}`}
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label="Sidebar"
      >
        <div
          ref={panelRef}
          data-testid="sidebar-panel"
          className={`${styles.panel} ${position === 'bottom' ? styles.bottom : ''} ${className}`}
          style={panelStyle}
          onClick={e => e.stopPropagation()}
          onTouchStart={isMobile && position === 'bottom' ? handleTouchStart : undefined}
          onTouchMove={isMobile && position === 'bottom' ? handleTouchMove : undefined}
          onTouchEnd={isMobile && position === 'bottom' ? handleTouchEnd : undefined}
        >
          {isMobile && position === 'bottom' && (
            <div className={styles.dragHandle} role="button" tabIndex={0} aria-label="Drag to close">
              <div className={styles.dragBar} />
            </div>
          )}
          <div className={styles.handle} onClick={toggleCollapse} role="button" aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <span className={styles.handleIcon}>{isCollapsed ? '›' : '‹'}</span>
          </div>
          <div className={styles.content}>{children}</div>
        </div>
      </div>
    </RightSidebarContext.Provider>
  );
};