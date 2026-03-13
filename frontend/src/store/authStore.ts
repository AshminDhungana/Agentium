import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/services/api';
import { jwtDecode } from 'jwt-decode';

// B6: extended role type to match the backend RBAC system
type UserRole =
    | 'primary_sovereign'
    | 'deputy_sovereign'
    | 'observer'
    | 'sovereign'   // sovereign backdoor fallback role
    | 'admin'       // legacy / convenience alias
    | 'user';       // legacy / convenience alias

interface User {
    id?: string;
    username: string;
    email?: string;
    is_active?: boolean;
    is_admin: boolean;
    is_pending?: boolean;
    is_sovereign?: boolean;  // B6: field returned by backend to_dict()
    created_at?: string;
    role?: UserRole;
    isAuthenticated: boolean;
    isSovereign?: boolean;
    agentium_id?: string;
}

// B5: result type for signup — avoids modifying the AuthState.isLoading /
//     error fields (which belong to the login flow) while still routing the
//     API call through a single service layer.
interface SignupResult {
    success: boolean;
    message: string;
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
    // B5: signup is now part of the store so all auth API calls go through
    //     one layer — no more direct api.post() calls from page components.
    signup: (username: string, email: string, password: string) => Promise<SignupResult>;
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

// B6: derive isSovereign from the role string returned by the backend.
//     The backend `to_dict()` returns `role: "primary_sovereign"` for admins
//     and `role: "sovereign"` for the backdoor fallback user.
//     Checking is_sovereign (from to_dict) covers the DB path; role string
//     covers both paths including the sovereign backdoor.
function deriveIsSovereign(user: {
    role?: string;
    is_admin?: boolean;
    is_sovereign?: boolean;
}): boolean {
    if (user.is_sovereign === true) return true;
    if (user.role === 'primary_sovereign') return true;
    if (user.role === 'sovereign') return true;
    return false;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            user: null,
            isInitialized: false,
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
                            is_sovereign: user.is_sovereign,
                            created_at: user.created_at,
                            isAuthenticated: true,
                            role: user.role ?? (user.is_admin ? 'admin' : 'user'),
                            // B6: use deriveIsSovereign instead of blindly equating
                            //     isSovereign to is_admin (not all admins are sovereign)
                            isSovereign: deriveIsSovereign(user),
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

            // B5: centralised signup call — SignupPage no longer calls api.post directly.
            //     Does NOT touch store-level isLoading/error (those belong to the login
            //     flow); the page manages its own local loading state for signup.
            signup: async (
                username: string,
                email: string,
                password: string,
            ): Promise<SignupResult> => {
                try {
                    const response = await api.post('/api/v1/auth/signup', {
                        username,
                        email,
                        password,
                    });

                    if (response.data.success) {
                        return {
                            success: true,
                            message:
                                response.data.message ||
                                'Account created successfully. Awaiting admin approval.',
                        };
                    }

                    return {
                        success: false,
                        message: response.data.message || 'Signup failed',
                    };
                } catch (error: any) {
                    // Normalise FastAPI validation errors and plain string details
                    let message = 'Signup failed. Please try again.';
                    const detail = error.response?.data?.detail;

                    if (Array.isArray(detail)) {
                        message = detail
                            .map((err: any) => `${err.loc?.join(' ')} — ${err.msg}`)
                            .join(', ');
                    } else if (typeof detail === 'string') {
                        message = detail;
                    } else if (error.message) {
                        message = error.message;
                    }

                    return { success: false, message };
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

                const hasPersistedUser = get().user?.isAuthenticated === true;
                if (!hasPersistedUser) {
                    set({ isLoading: true });
                }

                try {
                    // B2: removed `params: { token }` — the token is already attached to
                    //     every request as "Authorization: Bearer <token>" by api.ts's
                    //     request interceptor. Passing it as a query param also exposed
                    //     the JWT in server logs and browser history.
                    const response = await api.post('/api/v1/auth/verify', null);

                    if (response.data.valid) {
                        const userData = response.data.user;
                        set({
                            user: {
                                id: userData.user_id,
                                username: userData.username,
                                is_admin: userData.is_admin || false,
                                is_sovereign: userData.is_sovereign,
                                isAuthenticated: true,
                                role: userData.role ?? (userData.is_admin ? 'admin' : 'user'),
                                // B6: consistent isSovereign derivation
                                isSovereign: deriveIsSovereign(userData),
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
                                    isSovereign: deriveIsSovereign(decoded),
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
            // BEFORE any React component renders. Calling checkAuth() here
            // eliminates the race condition where isInitialized was false but the
            // router had already made a redirect decision.
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