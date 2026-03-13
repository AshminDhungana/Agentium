import { api } from './api';

export interface LoginCredentials {
    username: string;
    password: string;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    user: {
        username: string;
        is_admin: boolean;
        role?: string;
    };
}

export interface SessionUser {
    username: string;
    user_id: string;
    is_admin: boolean;
    role: string;
}

export interface VerifySessionResponse {
    valid: boolean;
    user: SessionUser;
}

export const authService = {
    /**
     * @deprecated Use `useAuthStore().login()` instead.
     *
     * This method duplicates the login logic that lives in `authStore.ts` and
     * is no longer called by any page component. It is kept here only for
     * backward compatibility with any external callers. New code should use
     * the Zustand store exclusively so that authentication state stays in sync
     * across the entire application.
     */
    async login(credentials: LoginCredentials): Promise<LoginResponse> {
        const response = await api.post('/api/v1/auth/login', credentials);

        localStorage.setItem('access_token', response.data.access_token);
        api.defaults.headers.common['Authorization'] = `Bearer ${response.data.access_token}`;

        return response.data;
    },

    /**
     * Verify the current token by hitting the backend verify endpoint.
     * The token is sent in the Authorization header (already set on the
     * shared `api` instance) rather than as a query parameter — query
     * params are visible in server logs and browser history.
     */
    async verifyToken(token: string): Promise<boolean> {
        try {
            const response = await api.post(
                '/api/v1/auth/verify',
                null,
                {
                    headers: { Authorization: `Bearer ${token}` },
                },
            );
            return response.data?.valid === true;
        } catch (error) {
            console.warn('Token verification failed:', error);
            return false;
        }
    },

    /**
     * Lightweight session check that returns the authenticated user profile.
     *
     * Unlike verifyToken() (which only returns a boolean), this endpoint
     * returns the full user context — useful for restoring session state on
     * page load, voice-bridge handshake, and any component that needs to
     * confirm identity without a full re-login.
     *
     * Maps to: GET /api/v1/auth/verify-session
     */
    async verifySession(): Promise<VerifySessionResponse> {
        const response = await api.get<VerifySessionResponse>(
            '/api/v1/auth/verify-session',
        );
        return response.data;
    },

    logout(): void {
        localStorage.removeItem('access_token');
        delete api.defaults.headers.common['Authorization'];
        window.location.href = '/login';
    },

    isAuthenticated(): boolean {
        return !!localStorage.getItem('access_token');
    },

    getToken(): string | null {
        return localStorage.getItem('access_token');
    },

    initAuth(): void {
        const token = localStorage.getItem('access_token');
        if (token) {
            api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        }
    },
};