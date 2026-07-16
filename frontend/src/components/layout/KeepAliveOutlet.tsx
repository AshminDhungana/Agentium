import { useOutlet, useLocation } from 'react-router-dom';
import { useState, useRef, useCallback, useEffect, useLayoutEffect, Suspense } from 'react';
import { Shield } from 'lucide-react';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { PAGE_LABELS } from './navConfig';

const OVERLAY_HOLD_MS = 1000;
const OVERLAY_FADE_MS = 300;
const PAGE_REVEAL_MS  = 320;
const RING_R = 28;
const RING_C = Math.round(2 * Math.PI * RING_R);

if (typeof document !== 'undefined') {
  const ID = 'agentium-page-transitions';
  if (!document.getElementById(ID)) {
    const s = document.createElement('style');
    s.id = ID;
    s.textContent = `
      :root { --ka-bg:#f9fafb; --ka-shield:#2563eb; --ka-ring:#3b82f6; --ka-track:#e5e7eb; --ka-label:#9ca3af; }
      html.dark { --ka-bg:#0f1117; --ka-shield:#60a5fa; --ka-ring:#3b82f6; --ka-track:#1e2535; --ka-label:#4b5563; }
      @keyframes kaShieldIn { from { opacity:0; transform:scale(0.72); } 65% { transform:scale(1.06); } to { opacity:1; transform:scale(1); } }
      @keyframes kaRingDraw { from { stroke-dashoffset:${RING_C}; } to { stroke-dashoffset:0; } }
      @keyframes kaLabelIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
      @keyframes kaOverlayOut { to { opacity:0; } }
      @keyframes kaPageReveal { from { opacity:0; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
    `;
    document.head.appendChild(s);
  }
}

function PageLoadOverlay({ pathname, isFadingOut, onFadeDone }: {
  pathname: string; isFadingOut: boolean; onFadeDone: () => void;
}) {
  const label = PAGE_LABELS[pathname] ?? 'Loading';
  return (
    <div
      onAnimationEnd={(e) => {
        if (isFadingOut && e.animationName === 'kaOverlayOut') onFadeDone();
      }}
      style={{
        position:'absolute', inset:0, zIndex:10, display:'flex', flexDirection:'column',
        alignItems:'center', justifyContent:'center', gap:'14px',
        backgroundColor:'var(--ka-bg)',
        animation: isFadingOut ? `kaOverlayOut ${OVERLAY_FADE_MS}ms ease forwards` : 'none',
      }}
    >
      <div style={{ position:'relative', width:'64px', height:'64px' }}>
        <svg width="64" height="64" viewBox="0 0 64 64" style={{ position:'absolute', inset:0, transform:'rotate(-90deg)' }} aria-hidden="true">
          <circle cx="32" cy="32" r={RING_R} fill="none" stroke="var(--ka-track)" strokeWidth="1.5" />
          <circle cx="32" cy="32" r={RING_R} fill="none" stroke="var(--ka-ring)" strokeWidth="2" strokeLinecap="round"
            strokeDasharray={RING_C} style={{ animation:`kaRingDraw 680ms cubic-bezier(0.4,0,0.2,1) 280ms both` }} />
        </svg>
        <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <Shield aria-hidden="true" style={{ width:'26px', height:'26px', color:'var(--ka-shield)', animation:'kaShieldIn 400ms cubic-bezier(0.34,1.4,0.64,1) both' }} />
        </div>
      </div>
      <span style={{ fontSize:'12px', color:'var(--ka-label)', fontWeight:400, letterSpacing:'0.04em', animation:'kaLabelIn 280ms ease 360ms both' }}>{label}</span>
    </div>
  );
}

function KeepAliveOutlet() {
  const location = useLocation();
  const currentOutlet = useOutlet();
  const cache = useRef<Map<string, React.ReactNode>>(new Map());
  const visited = useRef<Set<string>>(new Set());
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMounted = useRef(true);
  const [showOverlay, setShowOverlay] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);
  const [revealPath, setRevealPath] = useState<string | null>(null);
  const [cachedEntries, setCachedEntries] = useState<[string, React.ReactNode][]>([]);

  useEffect(() => { isMounted.current = true; return () => { isMounted.current = false; }; }, []);

  // Keep-alive cache is populated outside render (refs must not be read/written during render).
  useLayoutEffect(() => {
    if (currentOutlet) cache.current.set(location.pathname, currentOutlet);
    const next = Array.from(cache.current.entries());
    setCachedEntries((prev) => {
      if (prev.length === next.length) {
        const prevPaths = prev.map(([p]) => p).sort();
        const nextPaths = next.map(([p]) => p).sort();
        if (prevPaths.every((p, i) => p === nextPaths[i])) return prev;
      }
      return next;
    });
  }, [location.pathname, currentOutlet]);

  /* The page-load overlay must appear synchronously on first navigation and
     reset on revisit. These state transitions are driven by navigation (an
     effect) and cannot be derived during render, so the
     react-hooks/set-state-in-effect rule is disabled for this effect only. */
  /* eslint-disable react-hooks/set-state-in-effect */
  useLayoutEffect(() => {
    const path = location.pathname;
    const isFirst = !visited.current.has(path);
    if (holdTimer.current) { clearTimeout(holdTimer.current); holdTimer.current = null; }
    if (!isFirst) { setShowOverlay(false); setFadingOut(false); setRevealPath(null); return; }
    visited.current.add(path); setShowOverlay(true); setFadingOut(false); setRevealPath(null);
    holdTimer.current = setTimeout(() => {
      if (!isMounted.current) return;
      setFadingOut(true); setRevealPath(path);
    }, OVERLAY_HOLD_MS);
  }, [location.pathname]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => () => { if (holdTimer.current) clearTimeout(holdTimer.current); }, []);
  const handleOverlayDone = useCallback(() => { setShowOverlay(false); setFadingOut(false); }, []);

  return (
    <>
      {cachedEntries.map(([path, outlet]) => {
        const isActive = path === location.pathname;
        const isRevealing = revealPath === path;
        const isHeld = isActive && showOverlay && !isRevealing;
        return (
          <div key={path} style={{
            position:'absolute', inset:0, overflowY:'auto',
            opacity: isActive ? (isHeld ? 0 : 1) : 0,
            pointerEvents: isActive ? 'auto' : 'none',
            transition: (isRevealing || isHeld) ? 'none' : 'opacity 0.18s ease',
            animation: isRevealing ? `kaPageReveal ${PAGE_REVEAL_MS}ms cubic-bezier(0.25,0.1,0.25,1) forwards` : 'none',
          }}>
            <ErrorBoundary variant="widget" fallbackHeading="Page Load Failed">
              <Suspense fallback={<PageSkeleton />}>{outlet}</Suspense>
            </ErrorBoundary>
          </div>
        );
      })}
      {showOverlay && <PageLoadOverlay pathname={location.pathname} isFadingOut={fadingOut} onFadeDone={handleOverlayDone} />}
    </>
  );
}

function PageSkeleton() {
  return (
    <div className="absolute inset-0 flex flex-col gap-4 p-6 overflow-hidden">
      <div className="h-8 w-48 rounded-lg bg-gray-200 dark:bg-white/5 animate-pulse" />
      <div className="flex flex-col gap-3 mt-2">
        {[100, 85, 92, 78].map((w, i) => (
          <div key={i} className="h-4 rounded-md bg-gray-200 dark:bg-white/5 animate-pulse" style={{ width: `${w}%`, animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4 mt-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-32 rounded-xl bg-gray-200 dark:bg-white/5 animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
        ))}
      </div>
    </div>
  );
}

export { KeepAliveOutlet };
