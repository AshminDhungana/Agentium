import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/services/api';
import { jwtDecode } from 'jwt-decode';

// Proper User interface matching backend
interface User {
    id?: number;
    username: string;
    email?: string;
    is_active?: boolean;
    is_admin: boolean;
    is_pending?: boolean;
    created_at?: string;
    role?: 'admin' | 'user';
    isAuthenticated: boolean;
    isSovereign?: boolean;
    agentium_id?: string;
}

interface AuthState {
    user: User | null;
    // isInitialized: true once checkAuth() has run for the first time.
    // The app MUST NOT make any routing decisions until this is true.
    // It is intentionally NOT persisted so it always resets to false on page load.
    isInitialized: boolean;
    isLoading: boolean;
    error: string | null;
    login: (username: string, password: string) => Promise<boolean>;
    logout: () => void;
    changePassword: (oldPassword: string, newPassword: string) => Promise<boolean>;
    checkAuth: () => Promise<boolean>;
}

const extractUserFromToken = (token: string): Partial<User> | null => {
    try {
        const decoded = jwtDecode<any>(token);
        return {
            id: decoded.user_id,
            username: decoded.sub,
            is_admin: decoded.is_admin,
            is_active: decoded.is_active,
        };
    } catch {
        return null;
    }
};

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            user: null,
            isInitialized: false, // always starts false on page load — never persisted
            isLoading: false,
            error: null,

            login: async (username: string, password: string) => {
                set({ isLoading: true, error: null });

                try {
                    const response = await api.post('/api/v1/auth/login', {
                        username,
                        password,
                    });

                    const { access_token, user } = response.data;
                    localStorage.setItem('access_token', access_token);

                    set({
                        user: {
                            id: user.id,
                            username: user.username,
                            email: user.email,
                            is_active: user.is_active,
                            is_admin: user.is_admin,
                            is_pending: user.is_pending,
                            created_at: user.created_at,
                            isAuthenticated: true,
                            role: user.is_admin ? 'admin' : 'user',
                            isSovereign: user.is_admin,
                        },
                        isLoading: false,
                        isInitialized: true,
                        error: null,
                    });

                    return true;
                } catch (error: any) {
                    set({
                        error: error.response?.data?.detail || 'Invalid credentials',
                        isLoading: false,
                        isInitialized: true,
                    });
                    return false;
                }
            },

            logout: () => {
                localStorage.removeItem('access_token');
                set({ user: null, error: null, isInitialized: true });
            },

            changePassword: async (oldPassword: string, newPassword: string) => {
                set({ isLoading: true, error: null });

                try {
                    await api.post('/api/v1/auth/change-password', {
                        old_password: oldPassword,
                        new_password: newPassword,
                    });
                    set({ isLoading: false, error: null });
                    return true;
                } catch (error: any) {
                    let errorMsg = 'Failed to change password';

                    if (error.response?.data?.detail) {
                        if (Array.isArray(error.response.data.detail)) {
                            errorMsg = error.response.data.detail
                                .map((err: any) => err.msg || String(err))
                                .join(', ');
                        } else if (typeof error.response.data.detail === 'string') {
                            errorMsg = error.response.data.detail;
                        } else if (typeof error.response.data.detail === 'object') {
                            errorMsg =
                                error.response.data.detail.msg ||
                                JSON.stringify(error.response.data.detail);
                        }
                    } else if (error.message) {
                        errorMsg = error.message;
                    }

                    set({ error: errorMsg, isLoading: false });
                    return false;
                }
            },

            checkAuth: async () => {
                const token = localStorage.getItem('access_token');

                if (!token) {
                    set({ user: null, isInitialized: true });
                    return false;
                }

                // If persisted user exists, skip the loading spinner but still verify server-side
                const hasPersistedUser = get().user?.isAuthenticated === true;
                if (!hasPersistedUser) {
                    set({ isLoading: true });
                }

                try {
                    const response = await api.post('/api/v1/auth/verify', null, {
                        params: { token }
                    });

                    if (response.data.valid) {
                        const userData = response.data.user;
                        set({
                            user: {
                                id: userData.user_id,
                                username: userData.username,
                                is_admin: userData.is_admin || false,
                                isAuthenticated: true,
                                role: userData.role || (userData.is_admin ? 'admin' : 'user'),
                                isSovereign: userData.is_admin || false,
                            },
                            isLoading: false,
                            isInitialized: true,
                            error: null,
                        });
                        return true;
                    } else {
                        localStorage.removeItem('access_token');
                        set({ user: null, isLoading: false, isInitialized: true });
                        return false;
                    }
                } catch (error) {
                    console.error('Token verification failed:', error);

                    // Fallback: decode locally if server is temporarily down
                    try {
                        const decoded = extractUserFromToken(token);
                        if (decoded && decoded.username) {
                            set({
                                user: {
                                    ...decoded,
                                    username: decoded.username,
                                    is_admin: decoded.is_admin || false,
                                    isAuthenticated: true,
                                    isSovereign: decoded.is_admin || false,
                                } as User,
                                isLoading: false,
                                isInitialized: true,
                                error: null,
                            });
                            return true;
                        }
                    } catch (decodeError) {
                        console.error('Token decode failed:', decodeError);
                    }

                    if (!hasPersistedUser) {
                        localStorage.removeItem('access_token');
                        set({ user: null, isLoading: false, isInitialized: true });
                    } else {
                        set({ isLoading: false, isInitialized: true });
                    }
                    return hasPersistedUser;
                }
            },
        }),
        {
            name: 'auth-storage',
            // IMPORTANT: only persist `user`. Never persist isInitialized or isLoading —
            // isInitialized must always be false on a fresh page load.
            partialize: (state) => ({ user: state.user }),

            // onRehydrateStorage fires immediately after localStorage is read,
            // BEFORE any React component renders. This is the key fix:
            // by calling checkAuth() here we eliminate the race condition where
            // isInitialized was false but the router already made a redirect decision.
            onRehydrateStorage: () => (state) => {
                if (state) {
                    state.checkAuth();
                }
            },
        }
    )
);

export const useIsAuthenticated = (): boolean => {
    const user = useAuthStore((state) => state.user);
    return user?.isAuthenticated ?? false;
};

export const useIsAdmin = (): boolean => {
    const user = useAuthStore((state) => state.user);
    return user?.is_admin ?? false;
};