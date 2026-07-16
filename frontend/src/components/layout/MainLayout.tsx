import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { KeepAliveOutlet } from './KeepAliveOutlet';
import { getVisibleGroups, SOVEREIGN_ITEM, getPageTitle } from './navConfig';
import { useMediaQuery } from '@/hooks/useMediaQuery';

const COLLAPSE_KEY = 'agentium:sidebar-collapsed';

export function MainLayout() {
  const { user } = useAuthStore();
  const location = useLocation();
  const isAdmin = Boolean(user?.isSovereign || user?.is_admin);
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(COLLAPSE_KEY) === 'true';
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);

  const groups = getVisibleGroups(isAdmin);
  const sovereign = isAdmin ? SOVEREIGN_ITEM : undefined;
  const title = getPageTitle(location.pathname);

  useEffect(() => {
    if (isDesktop && mobileOpen) {
      const id = requestAnimationFrame(() => setMobileOpen(false));
      return () => cancelAnimationFrame(id);
    }
  }, [isDesktop, mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [mobileOpen]);

  useEffect(() => {
    if (mobileOpen) sidebarRef.current?.focus();
    else hamburgerRef.current?.focus();
  }, [mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen]);

  const toggleCollapse = () => {
    setCollapsed((c) => {
      const next = !c;
      window.localStorage.setItem(COLLAPSE_KEY, String(next));
      return next;
    });
  };

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-[#0f1117]">
      <Sidebar
        ref={sidebarRef}
        groups={groups}
        sovereignItem={sovereign}
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={title}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
          onOpenMobile={() => setMobileOpen(true)}
          hamburgerRef={hamburgerRef}
        />
        <main
          id="main-content"
          tabIndex={-1}
          className="relative min-h-0 flex-1 overflow-hidden outline-none"
        >
          <KeepAliveOutlet />
        </main>
      </div>
    </div>
  );
}

export default MainLayout;
