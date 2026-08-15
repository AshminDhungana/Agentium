// frontend/src/services/admin.ts
import { api } from './api';

// ── Budget types ──────────────────────────────────────────────────────────────

export interface BudgetData {
    current_limits: {
        daily_token_limit: number;
        daily_cost_limit: number;
    };
    usage: {
        tokens_used_today: number;
        tokens_remaining: number;
        cost_used_today_usd: number;
        cost_remaining_usd: number;
        cost_percentage_used: number;
        cost_percentage_tokens: number;
    };
    can_modify: boolean;
    optimizer_status: {
        idle_mode_active: boolean;
        time_since_last_activity_seconds: number;
    };
}

// ── User type ─────────────────────────────────────────────────────────────────
// FIX: id is a UUID string from PostgreSQL, not a number.
// Added role, is_sovereign, can_veto to match _user_dict() in admin.py.

export interface User {
    id: string;               // UUID from PostgreSQL — was incorrectly `number`
    username: string;
    email: string;
    is_active: boolean;
    is_admin: boolean;
    is_pending: boolean;
    role?: string;            // effective_role from backend (e.g. "primary_sovereign")
    is_sovereign?: boolean;   // true for sovereign users
    can_veto?: boolean;       // true for users with veto capability
    created_at?: string;
    updated_at?: string;
}

export interface UserListResponse {
    users: User[];
    total: number;
}

// ── Defaults ──────────────────────────────────────────────────────────────────

const defaultBudgetData: BudgetData = {
    current_limits: {
        daily_token_limit: 200000,
        daily_cost_limit: 100,
    },
    usage: {
        tokens_used_today: 0,
        tokens_remaining: 200000,
        cost_used_today_usd: 0,
        cost_remaining_usd: 100,
        cost_percentage_used: 0,
        cost_percentage_tokens: 0,
    },
    can_modify: false,
    optimizer_status: {
        idle_mode_active: false,
        time_since_last_activity_seconds: 0,
    },
};

// ── Service ───────────────────────────────────────────────────────────────────

export const adminService = {

    // ── Budget ────────────────────────────────────────────────────────────────

    async getBudget(): Promise<BudgetData> {
        try {
            const response = await api.get('/api/v1/admin/budget');
            if (!response.data) {
                console.warn('Budget endpoint returned empty data');
                return defaultBudgetData;
            }
            const mergedData: BudgetData = {
                current_limits: {
                    ...defaultBudgetData.current_limits,
                    ...response.data.current_limits,
                },
                usage: {
                    ...defaultBudgetData.usage,
                    ...response.data.usage,
                },
                can_modify: response.data.can_modify ?? defaultBudgetData.can_modify,
                optimizer_status: {
                    ...defaultBudgetData.optimizer_status,
                    ...response.data.optimizer_status,
                },
            };
            return mergedData;
        } catch (error: any) {
            console.warn('Budget endpoint error:', error.message);
            return defaultBudgetData;
        }
    },

    /** Raw budget status — used by FinancialBurnDashboard which does its own
     *  normalization of flat vs nested shapes. */
    async getBudgetStatus(): Promise<unknown> {
        const response = await api.get('/api/v1/admin/budget');
        return response.data;
    },

    async getBudgetHistory(days = 7): Promise<unknown> {
        const response = await api.get('/api/v1/admin/budget/history', {
            params: { days },
        });
        return response.data;
    },

    // ── User management ───────────────────────────────────────────────────────

    async getPendingUsers(): Promise<UserListResponse> {
        try {
            const response = await api.get<UserListResponse>('/api/v1/admin/users/pending');
            return response.data ?? { users: [], total: 0 };
        } catch (error) {
            console.error('Failed to fetch pending users:', error);
            return { users: [], total: 0 };
        }
    },

    /**
     * Fetch all approved users with optional server-side search.
     * The `search` param filters by username or email on the backend,
     * so it is efficient even with large user sets.
     */
    async getAllUsers(
        includePending = false,
        search?: string,
    ): Promise<UserListResponse> {
        try {
            const response = await api.get<UserListResponse>('/api/v1/admin/users', {
                params: {
                    include_pending: includePending,
                    ...(search ? { search } : {}),
                },
            });
            return response.data ?? { users: [], total: 0 };
        } catch (error) {
            console.error('Failed to fetch users:', error);
            return { users: [], total: 0 };
        }
    },

    // FIX: was userId: number — backend routes use UUID strings
    async approveUser(userId: string): Promise<{ success: boolean; message: string }> {
        const response = await api.post(`/api/v1/admin/users/${userId}/approve`);
        return response.data;
    },

    // FIX: was userId: number
    async rejectUser(userId: string): Promise<{ success: boolean; message: string }> {
        const response = await api.post(`/api/v1/admin/users/${userId}/reject`);
        return response.data;
    },

    // FIX: was userId: number
    async deleteUser(userId: string): Promise<{ success: boolean; message: string }> {
        const response = await api.delete(`/api/v1/admin/users/${userId}`);
        return response.data;
    },

    /**
     * Admin override: change any user's password.
     * Password is sent in the request body (not a query param) to avoid
     * it appearing in server access logs or browser history.
     * FIX: was userId: number
     */
    async changeUserPassword(
        userId: string,
        newPassword: string,
    ): Promise<{ success: boolean; message: string }> {
        const response = await api.post(
            `/api/v1/admin/users/${userId}/change-password`,
            { new_password: newPassword },
        );
        return response.data;
    },

    /**
     * Change a user's RBAC role.
     * Valid values: primary_sovereign | deputy_sovereign | observer
     * Maps to POST /api/v1/admin/users/{user_id}/role
     */
    async changeUserRole(
        userId: string,
        newRole: string,
    ): Promise<{
        success: boolean;
        message: string;
        previous_role?: string;
        new_role?: string;
    }> {
        const response = await api.post(
            `/api/v1/admin/users/${userId}/role`,
            { new_role: newRole },
        );
        return response.data;
    },

    /**
     * Change a user's active status (activate/deactivate).
     * Maps to PATCH /api/v1/admin/users/{user_id}/status
     */
    async changeUserStatus(
        userId: string,
        isActive: boolean,
    ): Promise<{ success: boolean; message: string; is_active: boolean }> {
        const response = await api.patch(
            `/api/v1/admin/users/${userId}/status`,
            { is_active: isActive },
        );
        return response.data;
    },
};