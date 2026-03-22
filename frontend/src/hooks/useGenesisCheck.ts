/**
 * useGenesisCheck
 *
 * Fires on every navigation (via location.pathname dep) while genesis is
 * incomplete, and once per session after it finishes (guarded by
 * sessionStorage).  Handles three backend states:
 *
 *   no_api_key  → toast + redirect to /models so the user adds a key
 *   pending     → API key exists but genesis not run → trigger POST /initialize
 *   ready       → fully operational, set session guard and do nothing
 *
 * Session guard rules:
 *   - SESSION_KEY is set ONLY when status === "ready" (not on no_api_key),
 *     so the check keeps re-running on every navigation until genesis is
 *     actually complete.
 *   - Cleared by authStore.logout() so the next login always re-checks.
 *
 * Genesis polling:
 *   After triggering POST /initialize the hook polls GET /status every 3 s
 *   until status === "ready" (or up to MAX_POLL_ATTEMPTS attempts). A toast
 *   notifies the user when the system finishes bootstrapping.
 */

import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

const SESSION_KEY       = 'genesis_check_done';
const POLL_INTERVAL_MS  = 3_000;
const MAX_POLL_ATTEMPTS = 20; // 60 s total ceiling

export function useGenesisCheck() {
    const navigate        = useNavigate();
    const location        = useLocation();
    const isAuthenticated = useAuthStore((s) => s.user?.isAuthenticated);
    // Include userId so the effect re-fires if a different user logs in
    // within the same tab without a full page reload.
    const userId          = useAuthStore((s) => s.user?.id);
    const pollTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Prevent the "add a key" toast + redirect from firing on every navigation
    // burst while the user is already heading to /models.
    const redirectedRef = useRef(false);

    // FIX (Bug 2): Prevent POST /initialize being fired more than once while
    // genesis is already running. Without this guard every navigation while
    // status === "pending" sends another POST, spawning a new background task
    // on the backend and multiplying the DB connection starvation described in
    // the genesis.py fix. The ref persists across re-renders and re-runs of
    // the effect so it survives rapid navigation between pages.
    const initInProgressRef = useRef(false);

    // Clean up any in-flight polling timer when the component unmounts.
    useEffect(() => () => {
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    }, []);

    // Re-run on every navigation (location.pathname) so that after the user
    // adds an API key on /models and navigates away, the pending → initialize
    // path fires immediately without requiring a logout/re-login.
    useEffect(() => {
        if (!isAuthenticated) return;
        if (sessionStorage.getItem(SESSION_KEY)) return;

        const token = localStorage.getItem('access_token');
        if (!token) return;

        const authHeaders = { Authorization: `Bearer ${token}` };

        // FIX (Bug 3): Use a per-run cancellation flag instead of relying
        // solely on pollTimerRef.
        //
        // The original code tracked only the most-recently-created timer in
        // pollTimerRef. When the effect re-fired (due to navigation) a new
        // polling chain started, but the previous chain's in-flight timers
        // continued running independently — pollTimerRef could only cancel
        // the last scheduled one, not every timer from every prior chain.
        // Over a few navigations this accumulated many concurrent chains all
        // hammering GET /genesis/status simultaneously.
        //
        // The fix: each effect run owns a `cancelled` boolean. The cleanup
        // function sets it to true, which every async callback in THIS run
        // checks before scheduling the next tick. Old chains are therefore
        // silenced as soon as the effect re-runs, regardless of how many
        // timers are still in the JS queue.
        let cancelled = false;

        // ── Poll until status === "ready" ─────────────────────────────────────
        let attempts = 0;
        function pollUntilReady() {
            if (cancelled) return; // this run was superseded — stop silently
            if (attempts >= MAX_POLL_ATTEMPTS) {
                toast.error('Genesis is taking longer than expected. Please refresh.');
                return;
            }
            attempts += 1;
            pollTimerRef.current = setTimeout(async () => {
                if (cancelled) return; // double-check after the async gap
                try {
                    const r = await fetch('/api/v1/genesis/status', { headers: authHeaders });
                    if (cancelled) return;
                    if (!r.ok) {
                        pollUntilReady();
                        return;
                    }
                    const data = await r.json();
                    if (data.status === 'ready') {
                        initInProgressRef.current = false;
                        sessionStorage.setItem(SESSION_KEY, 'true');
                        toast.success('System initialized and ready.', { icon: '🏛️', duration: 5_000 });
                    } else {
                        pollUntilReady(); // still pending — keep polling
                    }
                } catch {
                    if (!cancelled) pollUntilReady(); // network glitch — retry
                }
            }, POLL_INTERVAL_MS);
        }

        // ── Main status check ─────────────────────────────────────────────────
        fetch('/api/v1/genesis/status', { headers: authHeaders })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(async (data) => {
                if (cancelled) return;

                // ── Case 1: No API key — redirect to /models ──────────────────
                if (data.status === 'no_api_key') {
                    // FIX: do NOT set SESSION_KEY here.
                    // The old code set SESSION_KEY immediately, meaning after the
                    // user added a key on /models and navigated back, the guard
                    // blocked the check from ever running again — genesis never
                    // triggered and every page that needs agents/tasks failed.
                    // Now SESSION_KEY is only set when status === "ready", so the
                    // effect keeps re-checking on each navigation until genesis
                    // actually completes.

                    // Only redirect + toast once per navigation burst.
                    if (!redirectedRef.current && location.pathname !== '/models') {
                        redirectedRef.current = true;
                        toast('Add an AI provider key to begin Genesis.', {
                            icon: '🔑',
                            duration: 6_000,
                        });
                        navigate('/models', { replace: true });
                    }
                    return;
                }

                // Reset the redirect guard once a key exists so future
                // no_api_key transitions (e.g. key deleted) redirect again.
                redirectedRef.current = false;

                // ── Case 2: Key exists but genesis not run → trigger it ────────
                if (data.status === 'pending') {
                    // FIX (Bug 2): skip the POST if we already fired it.
                    // Without this guard, every navigation while genesis is still
                    // running sends another POST /initialize, spawning an extra
                    // background task and extra DB connections on the backend.
                    if (initInProgressRef.current) {
                        // Genesis already triggered — just poll for completion.
                        pollUntilReady();
                        return;
                    }

                    initInProgressRef.current = true;
                    try {
                        const initRes = await fetch('/api/v1/genesis/initialize', {
                            method:  'POST',
                            headers: authHeaders,
                        });
                        if (cancelled) return;
                        if (initRes.ok) {
                            const initData = await initRes.json();
                            if (initData.status === 'already_initialized') {
                                // Race condition: another tab finished first.
                                initInProgressRef.current = false;
                                sessionStorage.setItem(SESSION_KEY, 'true');
                            } else {
                                // "started" — poll until ready.
                                toast('Initializing Agentium governance system…', {
                                    icon: '🏛️',
                                    duration: 4_000,
                                });
                                pollUntilReady();
                            }
                        } else {
                            // Server rejected the request — allow a retry on the
                            // next navigation rather than locking initInProgressRef
                            // permanently true.
                            initInProgressRef.current = false;
                        }
                    } catch (err) {
                        console.warn('[GenesisCheck] Failed to trigger initialization:', err);
                        // Allow retry on next navigation.
                        initInProgressRef.current = false;
                    }
                    return;
                }

                // ── Case 3: Already ready ──────────────────────────────────────
                if (data.status === 'ready') {
                    initInProgressRef.current = false;
                    sessionStorage.setItem(SESSION_KEY, 'true');
                }
            })
            .catch((err) => {
                // Network or auth failure — leave key unset so we retry.
                console.warn('[GenesisCheck] Status check failed, will retry:', err);
                sessionStorage.removeItem(SESSION_KEY);
            });

        // Cleanup: mark this run as cancelled so its polling chain goes silent
        // the moment the effect re-runs (navigation) or the component unmounts.
        return () => {
            cancelled = true;
            if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        };

    // location.pathname is the critical addition: causes the check to re-run
    // on every navigation, so "add key on /models → navigate to dashboard"
    // immediately triggers genesis without needing a logout/re-login cycle.
    // userId guards against a different user logging in within the same tab.
    }, [isAuthenticated, userId, location.pathname, navigate]);
}