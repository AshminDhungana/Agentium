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
 *   - REDIRECT_KEY is set when we first redirect to /models for the
 *     no_api_key case, preventing repeated redirects on the same session.
 *     It is cleared when status transitions away from no_api_key (key added).
 *   - Both keys are cleared by authStore.logout() so the next login
 *     always re-checks from a clean state.
 *
 * ── Root Cause Fix ──────────────────────────────────────────────────────────
 * Previously a React ref (redirectedRef) was used to prevent duplicate
 * redirects to /models. A ref resets to false every time the component
 * unmounts and remounts (page refresh, route-level remount, etc.), so the
 * redirect fired on every page refresh while no API key was configured.
 *
 * The fix replaces redirectedRef with a sessionStorage key (REDIRECT_KEY).
 * sessionStorage survives page refreshes within the same tab but is cleared
 * on logout, giving us the correct "redirect exactly once per login session"
 * semantics without any component lifecycle dependency.
 * ────────────────────────────────────────────────────────────────────────────
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

// ── Session keys ──────────────────────────────────────────────────────────────

/**
 * Set once genesis reaches "ready".
 * Guards the entire hook from running once the system is fully initialized.
 */
export const GENESIS_SESSION_KEY = 'genesis_check_done';

/**
 * Set the FIRST time we redirect to /models due to a missing API key.
 * Prevents repeated redirects on the same login session (including after
 * page refreshes), while still being cleared the moment a key is added.
 *
 * Lifecycle:
 *   • Set   → when status === "no_api_key" and we navigate to /models
 *   • Clear → when status transitions to "pending" or "ready" (key exists)
 *   • Clear → on logout (via authStore.logout)
 */
export const GENESIS_REDIRECT_KEY = 'genesis_redirected_to_models';

// ── Constants ─────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS  = 3_000;
const MAX_POLL_ATTEMPTS = 20; // 60 s total ceiling

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useGenesisCheck() {
    const navigate        = useNavigate();
    const location        = useLocation();
    const isAuthenticated = useAuthStore((s) => s.user?.isAuthenticated);
    // Include userId so the effect re-fires if a different user logs in
    // within the same tab without a full page reload.
    const userId          = useAuthStore((s) => s.user?.id);
    const pollTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);

    // FIX (Bug 2): Prevent POST /initialize being fired more than once while
    // genesis is already running. Without this guard every navigation while
    // status === "pending" sends another POST, spawning a new background task
    // on the backend and multiplying DB connection starvation.
    const initInProgressRef = useRef(false);

    // Clean up any in-flight polling timer when the component unmounts.
    useEffect(() => () => {
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    }, []);

    useEffect(() => {
        if (!isAuthenticated) return;
        if (sessionStorage.getItem(GENESIS_SESSION_KEY)) return;

        const token = localStorage.getItem('access_token');
        if (!token) return;

        const authHeaders = { Authorization: `Bearer ${token}` };

        // FIX (Bug 3): Per-run cancellation flag — each navigation that
        // triggers a new effect run cancels the previous run's async chain.
        let cancelled = false;

        // ── Poll until status === "ready" ─────────────────────────────────────
        let attempts = 0;
        function pollUntilReady() {
            if (cancelled) return;
            if (attempts >= MAX_POLL_ATTEMPTS) {
                toast.error('Genesis is taking longer than expected. Please refresh.');
                return;
            }
            attempts += 1;
            pollTimerRef.current = setTimeout(async () => {
                if (cancelled) return;
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
                        sessionStorage.setItem(GENESIS_SESSION_KEY, 'true');
                        // Clear the redirect flag — genesis is done, no more
                        // redirecting needed even if user logs in again.
                        sessionStorage.removeItem(GENESIS_REDIRECT_KEY);
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

                // ── Case 1: No API key — redirect to /models (once per session) ──
                if (data.status === 'no_api_key') {
                    // FIX (Bug 1): Use sessionStorage instead of a React ref so
                    // this flag survives page refreshes within the same login
                    // session. A ref reset to false on every component remount,
                    // causing repeated redirects on page refresh.
                    const alreadyRedirected = sessionStorage.getItem(GENESIS_REDIRECT_KEY);

                    if (!alreadyRedirected && location.pathname !== '/models') {
                        // Mark as redirected BEFORE navigating so that the
                        // navigation-triggered effect re-run sees the flag.
                        sessionStorage.setItem(GENESIS_REDIRECT_KEY, 'true');
                        toast('Add an AI provider key to begin Genesis.', {
                            icon: '🔑',
                            duration: 6_000,
                        });
                        navigate('/models', { replace: true });
                    }
                    // Note: SESSION_KEY is intentionally NOT set here.
                    // The check must keep re-running until genesis actually
                    // completes (status reaches "ready").
                    return;
                }

                // Status is not no_api_key → a key has been added (or was
                // already present).  Clear the one-time redirect flag so that
                // if the key is later deleted and the user logs out/in, the
                // redirect will fire again on the new session.
                sessionStorage.removeItem(GENESIS_REDIRECT_KEY);

                // ── Case 2: Key exists but genesis not run → trigger it ────────
                if (data.status === 'pending') {
                    // FIX (Bug 2): skip the POST if we already fired it.
                    // Without this guard, every navigation while genesis is still
                    // running sends another POST /initialize.
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
                                sessionStorage.setItem(GENESIS_SESSION_KEY, 'true');
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
                    sessionStorage.setItem(GENESIS_SESSION_KEY, 'true');
                    sessionStorage.removeItem(GENESIS_REDIRECT_KEY);
                }
            })
            .catch((err) => {
                // Network or auth failure — leave key unset so we retry.
                console.warn('[GenesisCheck] Status check failed, will retry:', err);
                sessionStorage.removeItem(GENESIS_SESSION_KEY);
            });

        // Cleanup: mark this run as cancelled so its polling chain goes silent
        // the moment the effect re-runs (navigation) or the component unmounts.
        return () => {
            cancelled = true;
            if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        };

    // location.pathname is the critical dep: causes the check to re-run
    // on every navigation, so "add key on /models → navigate to dashboard"
    // immediately triggers genesis without needing a logout/re-login cycle.
    // userId guards against a different user logging in within the same tab.
    }, [isAuthenticated, userId, location.pathname, navigate]);
}