/**
 * useGenesisCheck
 *
 * Fires exactly once per login session, immediately after the user becomes
 * authenticated. If the backend reports no API key is configured, shows a
 * toast and redirects to /models so the user knows exactly what to do.
 *
 * sessionStorage is the correct scope here:
 *   - survives re-renders and React StrictMode double-invocations
 *   - clears when the tab closes → a new login always re-checks
 *   - authStore.logout() removes the key so the next login also re-checks
 *
 * Changes from original:
 *   1. Session guard is set INSIDE .then() (on success only) — previously it
 *      was set before the fetch, so any network/auth failure permanently
 *      suppressed the check for the rest of the session with no retry possible.
 *   2. .catch() removes the session key so the check retries on the next
 *      navigation, and logs a warning so failures are visible during development.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

const SESSION_KEY = 'genesis_check_done';

export function useGenesisCheck() {
    const navigate = useNavigate();

    // Only subscribe to the fields we actually need — avoids re-running the
    // effect every time an unrelated field on the user object changes.
    const isAuthenticated = useAuthStore((s) => s.user?.isAuthenticated);

    useEffect(() => {
        if (!isAuthenticated) return;

        // Guard: only run once per login session
        if (sessionStorage.getItem(SESSION_KEY)) return;

        // Token is read inside the effect (not as a store selector) because
        // authStore.login() writes to localStorage before setting isAuthenticated,
        // so by the time this effect fires the token is guaranteed to be present.
        const token = localStorage.getItem('access_token');

        if (!token) return;

        fetch('/api/v1/genesis/status', {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((r) => {
                if (!r.ok) {
                    // Treat HTTP errors the same as network errors — don't mark
                    // done so we retry on the next navigation.
                    throw new Error(`HTTP ${r.status}`);
                }
                return r.json();
            })
            .then((data) => {
                // Mark done only on a successful, parseable response so that
                // transient failures (server restart, slow boot) auto-recover.
                sessionStorage.setItem(SESSION_KEY, 'true');

                if (data.status === 'no_api_key') {
                    toast('Add an AI provider key to begin Genesis.', {
                        icon: '🔑',
                        duration: 6000,
                    });
                    // replace: true — back button won't loop the user back here
                    navigate('/models', { replace: true });
                }
            })
            .catch((err) => {
                // Non-fatal: don't block the user, but DO allow a retry by
                // leaving the session key unset.
                console.warn('[GenesisCheck] Status check failed, will retry:', err);
                sessionStorage.removeItem(SESSION_KEY);
            });
    }, [isAuthenticated, navigate]);
}