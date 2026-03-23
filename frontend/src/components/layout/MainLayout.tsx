// src/components/layout/MainLayout.tsx
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { NavLink, useNavigate, useLocation, useOutlet } from 'react-router-dom';
import {
    LayoutDashboard,
    Crown,
    Users,
    ClipboardList,
    Activity,
    BookOpen,
    Settings,
    LogOut,
    Cpu,
    Radio,
    Shield,
    Gavel,
    Inbox,
    FlaskConical,
} from 'lucide-react';
import { useState, useRef, useCallback, useEffect, Suspense } from 'react';
import { VoiceIndicator } from '@/components/VoiceIndicator';

// ─── Timing constants ─────────────────────────────────────────────────────────
//
//  Animation timeline for a first-visit page load:
//
//    0ms    Shield icon pops in        (spring scale, 400ms)
//    280ms  Progress ring starts draw  (stroke animation, 680ms)
//    360ms  Page label fades in        (280ms)
//    960ms  Ring completes             (280 + 680)
//   1000ms  Reveal triggered           (40ms buffer after ring finishes)
//   1000ms    ├─ Overlay fades out     (300ms)
//   1000ms    └─ Page reveals          (320ms, simultaneous)
//   1300ms  Complete
//
const OVERLAY_HOLD_MS = 1000;
const OVERLAY_FADE_MS = 300;
const PAGE_REVEAL_MS  = 320;

// SVG ring: r=28 → circumference = 2π×28 ≈ 175.93 → use 176
const RING_R = 28;
const RING_C = Math.round(2 * Math.PI * RING_R); // 176

// ─── Per-page labels ──────────────────────────────────────────────────────────
const PAGE_LABELS: Record<string, string> = {
    '/':             'Dashboard',
    '/chat':         'Command Interface',
    '/agents':       'Agents',
    '/tasks':        'Tasks',
    '/monitoring':   'Monitoring',
    '/voting':       'Voting',
    '/constitution': 'Constitution',
    '/models':       'Models',
    '/channels':     'Channels',
    '/message-log':  'Message Log',
    '/ab-testing':   'A/B Testing',
    '/settings':     'Settings',
    '/sovereign':    'Sovereign Control',
};

// ─── Global stylesheet (injected once) ───────────────────────────────────────
// Uses `html.dark` selector to match Tailwind's dark-mode strategy.
// CSS variables avoid duplicating color values.
if (typeof document !== 'undefined') {
    const ID = 'agentium-page-transitions';
    if (!document.getElementById(ID)) {
        const s = document.createElement('style');
        s.id = ID;
        s.textContent = `
            :root {
                --ka-bg:         #f9fafb;
                --ka-shield:     #2563eb;
                --ka-ring:       #3b82f6;
                --ka-track:      #e5e7eb;
                --ka-label:      #9ca3af;
            }
            html.dark {
                --ka-bg:         #0f1117;
                --ka-shield:     #60a5fa;
                --ka-ring:       #3b82f6;
                --ka-track:      #1e2535;
                --ka-label:      #4b5563;
            }
            @keyframes kaShieldIn {
                from { opacity:0; transform:scale(0.72); }
                65%  {            transform:scale(1.06); }
                to   { opacity:1; transform:scale(1);    }
            }
            @keyframes kaRingDraw {
                from { stroke-dashoffset:${RING_C}; }
                to   { stroke-dashoffset:0;         }
            }
            @keyframes kaLabelIn {
                from { opacity:0; transform:translateY(4px); }
                to   { opacity:1; transform:translateY(0);   }
            }
            @keyframes kaOverlayOut {
                to { opacity:0; }
            }
            @keyframes kaPageReveal {
                from { opacity:0; transform:translateY(7px); }
                to   { opacity:1; transform:translateY(0);   }
            }
        `;
        document.head.appendChild(s);
    }
}

// ─── PageLoadOverlay ──────────────────────────────────────────────────────────
interface PageLoadOverlayProps {
    pathname:    string;
    isFadingOut: boolean;
    onFadeDone:  () => void;
}

function PageLoadOverlay({ pathname, isFadingOut, onFadeDone }: PageLoadOverlayProps) {
    const label = PAGE_LABELS[pathname] ?? 'Loading';

    return (
        <div
            onAnimationEnd={(e) => {
                // Guard: onAnimationEnd fires for every child animation too.
                // Only call onFadeDone when the overlay's own fade completes.
                if (isFadingOut && e.animationName === 'kaOverlayOut') {
                    onFadeDone();
                }
            }}
            style={{
                position:        'absolute',
                inset:           0,
                zIndex:          10,
                display:         'flex',
                flexDirection:   'column',
                alignItems:      'center',
                justifyContent:  'center',
                gap:             '14px',
                backgroundColor: 'var(--ka-bg)',
                animation: isFadingOut
                    ? `kaOverlayOut ${OVERLAY_FADE_MS}ms ease forwards`
                    : 'none',
            }}
        >
            {/* Shield icon + orbital progress ring */}
            <div style={{ position:'relative', width:'64px', height:'64px' }}>

                {/* Rotate -90° so the ring draws from the top (12-o'clock) */}
                <svg
                    width="64" height="64" viewBox="0 0 64 64"
                    style={{ position:'absolute', inset:0, transform:'rotate(-90deg)' }}
                    aria-hidden="true"
                >
                    {/* Faint track */}
                    <circle
                        cx="32" cy="32" r={RING_R}
                        fill="none"
                        stroke="var(--ka-track)"
                        strokeWidth="1.5"
                    />
                    {/* Animated fill ring */}
                    <circle
                        cx="32" cy="32" r={RING_R}
                        fill="none"
                        stroke="var(--ka-ring)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeDasharray={RING_C}
                        style={{
                            // `both` fill-mode: starts fully hidden before the 280ms delay
                            animation: `kaRingDraw 680ms cubic-bezier(0.4,0,0.2,1) 280ms both`,
                        }}
                    />
                </svg>

                {/* Shield centered over the ring */}
                <div style={{
                    position:'absolute', inset:0,
                    display:'flex', alignItems:'center', justifyContent:'center',
                }}>
                    <Shield
                        aria-hidden="true"
                        style={{
                            width: '26px', height: '26px',
                            color: 'var(--ka-shield)',
                            // Spring overshoot (1.4 amplitude) for a confident snap-in feel
                            animation: 'kaShieldIn 400ms cubic-bezier(0.34,1.4,0.64,1) both',
                        }}
                    />
                </div>
            </div>

            {/* Page label — fades in after icon is settled */}
            <span style={{
                fontSize:      '12px',
                color:         'var(--ka-label)',
                fontWeight:    400,
                letterSpacing: '0.04em',
                animation:     'kaLabelIn 280ms ease 360ms both',
            }}>
                {label}
            </span>
        </div>
    );
}

// ─── KeepAliveOutlet ──────────────────────────────────────────────────────────
// Keeps every visited page in the DOM; only active page is visible (opacity:1).
//
// State machine per navigation:
//
//   FIRST VISIT
//     ├─ showOverlay → true  (overlay renders above content)
//     ├─ page renders hidden under overlay (opacity:0, transition:none)
//     ├─ after OVERLAY_HOLD_MS:
//     │    ├─ fadingOut → true   (triggers kaOverlayOut on overlay div)
//     │    └─ revealPath → path  (triggers kaPageReveal on page div)
//     └─ after overlay animation: showOverlay → false, overlay unmounts
//
//   REVISIT
//     ├─ Any active overlay state is cleared
//     └─ CSS transition opacity 0→1 (180ms) — smooth, no overlay
//
//   GO INACTIVE
//     └─ CSS transition opacity 1→0 (180ms)
//
function KeepAliveOutlet() {
    const location      = useLocation();
    const currentOutlet = useOutlet();

    const cache      = useRef<Map<string, React.ReactNode>>(new Map());
    const visited    = useRef<Set<string>>(new Set());
    const holdTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isMounted  = useRef(true);

    const [showOverlay, setShowOverlay] = useState(false);
    const [fadingOut,   setFadingOut]   = useState(false);
    const [revealPath,  setRevealPath]  = useState<string | null>(null);

    useEffect(() => {
        isMounted.current = true;
        return () => { isMounted.current = false; };
    }, []);

    // Always update the cache with the current outlet
    if (currentOutlet) {
        cache.current.set(location.pathname, currentOutlet);
    }

    useEffect(() => {
        const path    = location.pathname;
        const isFirst = !visited.current.has(path);

        // Cancel any pending reveal from a previous navigation
        if (holdTimer.current) {
            clearTimeout(holdTimer.current);
            holdTimer.current = null;
        }

        if (!isFirst) {
            // Revisit — clear any leftover overlay state and use CSS transition
            setShowOverlay(false);
            setFadingOut(false);
            setRevealPath(null);
            return;
        }

        // First visit — mark, show overlay, schedule reveal
        visited.current.add(path);
        setShowOverlay(true);
        setFadingOut(false);
        setRevealPath(null);

        holdTimer.current = setTimeout(() => {
            if (!isMounted.current) return;
            setFadingOut(true);
            setRevealPath(path);
        }, OVERLAY_HOLD_MS);
    }, [location.pathname]);

    // Cleanup on unmount
    useEffect(() => () => { if (holdTimer.current) clearTimeout(holdTimer.current); }, []);

    const handleOverlayDone = useCallback(() => {
        setShowOverlay(false);
        setFadingOut(false);
    }, []);

    return (
        <>
            {Array.from(cache.current.entries()).map(([path, outlet]) => {
                const isActive    = path === location.pathname;
                const isRevealing = revealPath === path;
                // During hold phase: keep page invisible under the overlay
                const isHeld      = isActive && showOverlay && !isRevealing;

                return (
                    <div
                        key={path}
                        style={{
                            position:      'absolute',
                            inset:         0,
                            overflowY:     'auto',
                            opacity:       isActive ? (isHeld ? 0 : 1) : 0,
                            pointerEvents: isActive ? 'auto' : 'none',
                            // Suppress CSS transition while keyframe animations are running
                            transition:    (isRevealing || isHeld) ? 'none' : 'opacity 0.18s ease',
                            animation:     isRevealing
                                ? `kaPageReveal ${PAGE_REVEAL_MS}ms cubic-bezier(0.25,0.1,0.25,1) forwards`
                                : 'none',
                        }}
                    >
                        {outlet}
                    </div>
                );
            })}

            {showOverlay && (
                <PageLoadOverlay
                    pathname={location.pathname}
                    isFadingOut={fadingOut}
                    onFadeDone={handleOverlayDone}
                />
            )}
        </>
    );
}

// ─── PageSkeleton ─────────────────────────────────────────────────────────────
// Only shown while React.lazy() fetches the JS chunk for the first time.
// After that, KeepAliveOutlet serves from cache — this never renders again.
function PageSkeleton() {
    return (
        <div className="absolute inset-0 flex flex-col gap-4 p-6 overflow-hidden">
            <div className="h-8 w-48 rounded-lg bg-gray-200 dark:bg-white/5 animate-pulse" />
            <div className="flex flex-col gap-3 mt-2">
                {[100, 85, 92, 78].map((w, i) => (
                    <div
                        key={i}
                        className="h-4 rounded-md bg-gray-200 dark:bg-white/5 animate-pulse"
                        style={{ width: `${w}%`, animationDelay: `${i * 60}ms` }}
                    />
                ))}
            </div>
            <div className="grid grid-cols-3 gap-4 mt-4">
                {[0, 1, 2].map(i => (
                    <div
                        key={i}
                        className="h-32 rounded-xl bg-gray-200 dark:bg-white/5 animate-pulse"
                        style={{ animationDelay: `${i * 80}ms` }}
                    />
                ))}
            </div>
        </div>
    );
}

// ─── MainLayout ───────────────────────────────────────────────────────────────
export function MainLayout() {
    const { user, logout } = useAuthStore();
    const navigate    = useNavigate();
    const unreadCount = useWebSocketStore(state => state.unreadCount);
    const [isDark, setIsDark] = useState(() =>
        typeof window !== 'undefined'
            ? document.documentElement.classList.contains('dark')
            : false
    );
    const isAdmin = user?.isSovereign || user?.is_admin || false;

    const handleLogout = () => {
        window.dispatchEvent(new Event('logout'));
        logout();
        navigate('/login');
    };

    const toggleTheme = () => {
        const next = !isDark;
        setIsDark(next);
        document.documentElement.classList.toggle('dark', next);
        localStorage.setItem('theme', next ? 'dark' : 'light');
    };

    const prefetch = useCallback((path: string) => {
        switch (path) {
            case '/chat':         import('@/pages/ChatPage');           break;
            case '/agents':       import('@/pages/AgentsPage');         break;
            case '/tasks':        import('@/pages/TasksPage');          break;
            case '/monitoring':   import('@/pages/MonitoringPage');     break;
            case '/voting':       import('@/pages/VotingPage');         break;
            case '/constitution': import('@/pages/ConstitutionPage');   break;
            case '/models':       import('@/pages/ModelsPage');         break;
            case '/channels':     import('@/pages/ChannelsPage');       break;
            case '/message-log':  import('@/pages/MessageLogPage');     break;
            case '/ab-testing':   import('@/pages/ABTestingPage');      break;
            case '/settings':     import('@/pages/SettingsPage');       break;
            case '/sovereign':    import('@/pages/SovereignDashboard'); break;
            default:              import('@/pages/Dashboard');          break;
        }
    }, []);

    type NavItem = {
        path:       string;
        label:      string;
        icon:       React.ComponentType<{ className?: string }>;
        badge?:     number;
        variant?:   'default' | 'danger';
        adminOnly?: boolean;
    };

    const navItems: NavItem[] = [
        { path: '/',             label: 'Dashboard',         icon: LayoutDashboard },
        { path: '/chat',         label: 'Command Interface', icon: Crown,
          badge: unreadCount > 0 ? unreadCount : undefined },
        { path: '/agents',       label: 'Agents',            icon: Users },
        { path: '/tasks',        label: 'Tasks',             icon: ClipboardList },
        { path: '/monitoring',   label: 'Monitoring',        icon: Activity },
        { path: '/voting',       label: 'Voting',            icon: Gavel },
        { path: '/constitution', label: 'Constitution',      icon: BookOpen },
        { path: '/models',       label: 'Models',            icon: Cpu },
        { path: '/channels',     label: 'Channels',          icon: Radio },
        { path: '/message-log',  label: 'Message Log',       icon: Inbox },
        { path: '/ab-testing',   label: 'A/B Testing',       icon: FlaskConical, adminOnly: true },
        { path: '/settings',     label: 'Settings',          icon: Settings },
        ...(isAdmin
            ? [{ path: '/sovereign', label: 'Sovereign Control', icon: Shield, variant: 'danger' as const }]
            : []),
    ];

    const visibleNavItems = navItems.filter(item => !item.adminOnly || isAdmin);

    return (
        <div className="h-screen bg-gray-50 dark:bg-[#0f1117] flex">
            {/* ── Sidebar ───────────────────────────────────────────────── */}
            <aside className="w-64 bg-white dark:bg-[#161b27] border-r border-gray-200 dark:border-[#1e2535] flex flex-col">
                <div className="px-4 py-3 border-b border-gray-200 dark:border-[#1e2535] flex-shrink-0">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={toggleTheme}
                            className="group relative p-2 rounded-xl transition-all duration-300 hover:bg-gray-100 dark:hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                        >
                            <Shield className="w-8 h-8 text-blue-600 transition-all duration-300 rotate-0 scale-100 dark:rotate-90 dark:scale-0 dark:opacity-0" />
                            <Shield className="w-8 h-8 absolute inset-0 m-auto text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.5)] transition-all duration-300 rotate-90 scale-0 opacity-0 dark:rotate-0 dark:scale-100 dark:opacity-100" />
                        </button>
                        <div>
                            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Agentium</h1>
                            <p className="text-xs text-gray-500 dark:text-blue-400/70">AI Governance</p>
                        </div>
                    </div>
                </div>

                <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-hidden">
                    {visibleNavItems.map((item) => (
                        <div key={item.path}>
                            {item.variant === 'danger' && (
                                <div className="my-1.5 border-t border-gray-200 dark:border-[#1e2535]" />
                            )}
                            <NavLink
                                to={item.path}
                                end={item.path === '/'}
                                onMouseEnter={() => prefetch(item.path)}
                                className={({ isActive }) =>
                                    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                                        item.variant === 'danger'
                                            ? isActive
                                                ? 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300 border border-red-200 dark:border-red-500/20'
                                                : 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 bg-red-50/50 dark:bg-red-500/5'
                                            : isActive
                                                ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                                                : 'text-gray-700 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
                                    }`
                                }
                            >
                                <item.icon className={`w-[18px] h-[18px] flex-shrink-0 ${item.variant === 'danger' ? 'text-red-500' : ''}`} />
                                <span className="flex-1">{item.label}</span>
                                {item.badge !== undefined && (
                                    <span className="bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
                                        {item.badge > 9 ? '9+' : item.badge}
                                    </span>
                                )}
                            </NavLink>
                        </div>
                    ))}
                </nav>

                <div className="px-4 py-3 border-t border-gray-200 dark:border-[#1e2535]">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-sm font-bold">
                            {user?.username?.charAt(0).toUpperCase() || 'U'}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                {user?.username || 'User'}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                                {user?.role || 'Member'}
                            </p>
                        </div>
                        <VoiceIndicator iconOnly />
                    </div>
                    <button
                        onClick={handleLogout}
                        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        Logout
                    </button>
                </div>
            </aside>

            {/* ── Main content ──────────────────────────────────────────── */}
            {/* position:relative anchors all absolutely-positioned children */}
            <main className="flex-1 min-h-0 overflow-hidden relative">
                <Suspense fallback={<PageSkeleton />}>
                    <KeepAliveOutlet />
                </Suspense>
            </main>
        </div>
    );
}