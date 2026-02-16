import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/services/api';
import { jwtDecode } from 'jwt-decode';

// Proper User interface matching backend
interface User {
    id?: number;           // Database ID (integer) - optional because verify doesn't return it
    username: string;
    email?: string;        // Optional because verify doesn't return it
    is_active?: boolean;
    is_admin: boolean;
    is_pending?: boolean;
    created_at?: string;
    role?: "admin" | "user";
    isAuthenticated: boolean;
    isSovereign?: boolean;
    agentium_id?: string;
}

interface AuthState {
    user: User | null;
    login: (username: string, password: string) => Promise<boolean>;
    logout: () => void;
    changePassword: (oldPassword: string, newPassword: string) => Promise<boolean>;
    isLoading: boolean;
    error: string | null;
    checkAuth: () => Promise<boolean>;
}

// Clean helper for token decoding
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
            isLoading: false,
            error: null,

            login: async (username: string, password: string) => {
                set({ isLoading: true, error: null });

                try {
                    const response = await api.post('/api/v1/auth/login', {
                        username,
                        password
                    });

                    const { access_token, user } = response.data;

                    // Store JWT token
                    localStorage.setItem('access_token', access_token);

                    // Use the user object from API response (fully populated)
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
                            role: user.is_admin ? "admin" : "user",
                            isSovereign: user.is_admin,
                        },
                        isLoading: false,
                        error: null
                    });

                    return true;
                } catch (error: any) {
                    set({
                        error: error.response?.data?.detail || 'Invalid credentials',
                        isLoading: false
                    });
                    return false;
                }
            },

            logout: () => {
                localStorage.removeItem('access_token');
                set({ user: null, error: null });
            },

            changePassword: async (oldPassword: string, newPassword: string) => {
                set({ isLoading: true, error: null });

                try {
                    await api.post('/api/v1/auth/change-password', {
                        old_password: oldPassword,
                        new_password: newPassword
                    });

                    set({ isLoading: false, error: null });
                    return true;
                } catch (error: any) {
                    // Extract error message properly from FastAPI validation errors
                    let errorMsg = 'Failed to change password';
                    
                    if (error.response?.data?.detail) {
                        // Handle FastAPI validation error format (array of errors)
                        if (Array.isArray(error.response.data.detail)) {
                            errorMsg = error.response.data.detail
                                .map((err: any) => err.msg || String(err))
                                .join(', ');
                        } else if (typeof error.response.data.detail === 'string') {
                            errorMsg = error.response.data.detail;
                        } else if (typeof error.response.data.detail === 'object') {
                            errorMsg = error.response.data.detail.msg || JSON.stringify(error.response.data.detail);
                        }
                    } else if (error.message) {
                        errorMsg = error.message;
                    }
                    
                    set({
                        error: errorMsg,
                        isLoading: false
                    });
                    return false;
                }
            },

            checkAuth: async () => {
                const token = localStorage.getItem('access_token');

                if (!token) {
                    set({ user: null });
                    return false;
                }

                try {
                    // FIXED: Backend expects token as a string parameter in the body
                    const response = await api.post('/api/v1/auth/verify', token, {
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });

                    if (response.data.valid) {
                        const userData = response.data.user;

                        // FIXED: Use only fields that verify endpoint returns
                        set({
                            user: {
                                id: userData.user_id,
                                username: userData.username,
                                is_admin: userData.is_admin || false,
                                isAuthenticated: true,
                                role: userData.role || (userData.is_admin ? "admin" : "user"),
                                isSovereign: userData.is_admin || false,
                            },
                            error: null
                        });
                        return true;
                    } else {
                        localStorage.removeItem('access_token');
                        set({ user: null });
                        return false;
                    }
                } catch (error) {
                    console.error('Token verification failed:', error);

                    // If verify fails, try to decode token locally as fallback
                    try {
                        const decoded = extractUserFromToken(token);
                        if (decoded && decoded.username) {
                            console.log('Using local token decode as fallback');
                            set({
                                user: {
                                    ...decoded,
                                    username: decoded.username,
                                    is_admin: decoded.is_admin || false,
                                    isAuthenticated: true,
                                    isSovereign: decoded.is_admin || false,
                                } as User,
                                error: null
                            });
                            return true;
                        }
                    } catch (decodeError) {
                        console.error('Token decode failed:', decodeError);
                    }

                    localStorage.removeItem('access_token');
                    set({ user: null });
                    return false;
                }
            }
        }),
        {
            name: 'auth-storage',
            partialize: (state) => ({
                user: state.user
            })
        }
    )
);

// Convenience hook for checking authentication
export const useIsAuthenticated = (): boolean => {
    const user = useAuthStore(state => state.user);
    return user?.isAuthenticated ?? false;
};

// Convenience hook for checking admin
export const useIsAdmin = (): boolean => {
    const user = useAuthStore(state => state.user);
    return user?.is_admin ?? false;
};