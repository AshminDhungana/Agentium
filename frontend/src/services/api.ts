import axios from 'axios';
import toast from 'react-hot-toast';

const API_URL = import.meta.env.VITE_API_BASE_URL || '';

/** Maximum number of times a 429 response will be automatically retried. */
const MAX_RATE_LIMIT_RETRIES = 3;

export const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// ── Attach JWT to every request ───────────────────────────────────────────────
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// ── Global error handling ─────────────────────────────────────────────────────
api.interceptors.response.use(
    (response) => response,
    (error) => {
        const status  = error.response?.status;
        const message = error.response?.data?.detail || error.message || 'An unexpected error occurred';

        if (status === 401) {
            // FIX: Do NOT call logout() when the 401 comes from the token
            // verification endpoint itself (/auth/verify).  checkAuth() already
            // handles that path (it clears the token and sets user to null in its
            // own catch block).  Calling logout() here as well creates two
            // concurrent state writes with stale closure values, which can leave
            // isInitialized in an inconsistent state and prevent the login page
            // from rendering correctly after a logout/re-login cycle.
            const isVerifyCall = error.config?.url?.includes('/auth/verify');

            if (!isVerifyCall && !window.location.pathname.includes('/login')) {
                localStorage.removeItem('access_token');
                // Note: deleting from defaults is redundant (the request
                // interceptor reads directly from localStorage) but kept for
                // safety in case any code sets a default header directly.
                delete api.defaults.headers.common['Authorization'];
                import('@/store/authStore').then(({ useAuthStore }) => {
                    useAuthStore.getState().logout();
                });
            }
        } else if (status === 403) {
            toast.error(`Permission Denied: ${message}`);
        } else if (status === 404) {
            // Suppress 404 toasts for GET requests — handled by the component.
            if (error.config?.method !== 'get') {
                toast.error(`Not Found: ${message}`);
            }
        } else if (status >= 500) {
            // Suppress server-error toasts for endpoints that handle 5xx themselves.
            const silentPaths = ['/api/v1/chat/history'];
            const isSilent = silentPaths.some((p) => error.config?.url?.includes(p));
            if (!isSilent) {
                toast.error(`Server Error: ${message}`);
            }
        } else if (status === 429) {
            // Rate limited — retry after the suggested delay (default 5 s).
            // Guard: track retry count on the config object to prevent infinite loops.
            const config = error.config as typeof error.config & { _rateLimitRetries?: number };
            const retries = config._rateLimitRetries ?? 0;

            if (retries < MAX_RATE_LIMIT_RETRIES) {
                const retryAfter = parseInt(error.response?.headers?.['retry-after'] || '5', 10);
                config._rateLimitRetries = retries + 1;
                return new Promise((resolve, reject) => {
                    setTimeout(() => {
                        api.request(config).then(resolve).catch(reject);
                    }, retryAfter * 1000);
                });
            } else {
                // Exceeded retry budget — surface error to caller.
                toast.error('Rate limit exceeded. Please try again later.');
            }
        } else if (status !== undefined && status !== 401) {
            // 400, 422, etc. — show the detail message.
            toast.error(message);
        }

        return Promise.reject(error);
    },
);

// ── Channel type helpers ──────────────────────────────────────────────────────

export type ChannelTypeSlug =
    | 'whatsapp'
    | 'slack'
    | 'telegram'
    | 'email'
    | 'discord'
    | 'signal'
    | 'google_chat'
    | 'teams'
    | 'zalo'
    | 'matrix'
    | 'imessage'
    | 'custom';

export type ChannelStatus = 'pending' | 'active' | 'error' | 'disconnected';

export interface Channel {
    id: string;
    name: string;
    type: ChannelTypeSlug;
    status: ChannelStatus;
    config: {
        phone_number?: string;
        has_credentials: boolean;
        webhook_url?: string;
        homeserver_url?: string;
        oa_id?: string;
        backend?: string;
        number?: string;
        bb_url?: string;
    };
    routing: {
        default_agent?: string;
        auto_create_tasks: boolean;
        require_approval: boolean;
    };
    stats: {
        received: number;
        sent: number;
        last_message?: string;
    };
}

// ── WebSocket event types ─────────────────────────────────────────────────────

export type WebSocketEventType =
    | 'agent_spawned'
    | 'task_escalated'
    | 'vote_initiated'
    | 'constitutional_violation'
    | 'message_routed'
    | 'knowledge_submitted'
    | 'knowledge_approved'
    | 'amendment_proposed'
    | 'agent_liquidated'
    | 'system'
    | 'status'
    | 'message'
    | 'error'
    | 'pong';

export interface WebSocketEvent {
    type: WebSocketEventType;
    timestamp: string;
    [key: string]: unknown;
}