import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/services/api';

interface User {
    id: string;
    username: string;
    role: string;
    isAuthenticated: boolean;
    isSovereign?: boolean;
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

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            user: null,
            isLoading: false,
            error: null,

            login: async (username: string, password: string) => {
                set({
                    user: {
                        ...user,
                        isAuthenticated: true,
                        isSovereign: user.role === 'admin' || user.username === 'sovereign'
                    },
                    isLoading: false,
                    error: null
                });

                try {
                    const response = await api.post('/auth/login', {
                        username,
                        password
                    });

                    const { access_token, user } = response.data;

                    // Store JWT token
                    localStorage.setItem('access_token', access_token);

                    set({
                        user: {
                            ...user,
                            isAuthenticated: true
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
                    // Call backend to change password (endpoint would need to be created)
                    await api.post('/auth/change-password', {
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
                    // Verify token with backend
                    const response = await api.post('/auth/verify', { token });

                    if (response.data.valid) {
                        set({
                            user: { ...response.data.user, isAuthenticated: true },
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
            partialize: (state) => ({ user: state.user })
        }
    )
);