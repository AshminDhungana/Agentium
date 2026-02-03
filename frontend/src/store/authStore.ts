import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/services/api';
import { jwtDecode } from 'jwt-decode';

//  Proper User interface matching backend
interface User {
    id: number;           // Database ID (integer)
    username: string;
    email: string;
    is_active: boolean;
    is_admin: boolean;
    is_pending: boolean;
    created_at?: string;
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

//  Clean helper for token decoding
const extractUserFromToken = (token: string): Partial<User> | null => {
    try {
        const decoded = jwtDecode<any>(token);
        return {
            id: decoded.user_id,
            username: decoded.sub,
            is_admin: decoded.is_admin,
            is_active: decoded.is_active,
            // Note: email might not be in token, will be fetched from API
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

                    //  Use the user object from API response (fully populated)
                    set({
                        user: {
                            id: user.id,
                            username: user.username,
                            email: user.email,
                            is_active: user.is_active,
                            is_admin: user.is_admin,
                            is_pending: user.is_pending,
                            created_at: user.created_at,
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
                    set({
                        error: error.response?.data?.detail || 'Failed to change password',
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
                    const response = await api.post('/api/v1/auth/verify', { token });

                    if (response.data.valid) {
                        const userData = response.data.user;

                        //  Use API response directly
                        set({
                            user: {
                                id: userData.id,
                                username: userData.username,
                                email: userData.email,
                                is_active: userData.is_active,
                                is_admin: userData.is_admin,
                                is_pending: userData.is_pending,
                                created_at: userData.created_at,
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

//  Convenience hook for checking authentication
export const useIsAuthenticated = (): boolean => {
    const user = useAuthStore(state => state.user);
    return user !== null;
};

// Convenience hook for checking admin
export const useIsAdmin = (): boolean => {
    const user = useAuthStore(state => state.user);
    return user?.is_admin ?? false;
};