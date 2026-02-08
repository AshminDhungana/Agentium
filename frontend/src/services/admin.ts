// services/admin.ts
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '';

export interface BudgetData {
    total_budget: number;
    total_spent: number;
    total_remaining: number;
    percentage_used: number;
    tokens_used: number;
    tokens_limit: number;
    tokens_remaining: number;
    last_reset: string;
    status: 'healthy' | 'warning' | 'critical';
}

export interface User {
    id: number;
    username: string;
    email: string;
    is_active: boolean;
    is_admin: boolean;
    is_pending: boolean;
    created_at?: string;
    updated_at?: string;
}

export interface UserListResponse {
    users: User[];
    total: number;
}

export const adminService = {
    /**
     * Get current API budget with safe error handling
     */
    async getBudget(): Promise<BudgetData | null> {
        try {
            const response = await axios.get(`${API_URL}/api/v1/admin/budget`);
            return response.data;
        } catch (error: any) {
            console.warn('Budget endpoint not available:', error.message);
            // Return null instead of throwing - let component handle it gracefully
            return null;
        }
    },

    /**
     * Get all pending users
     */
    async getPendingUsers(): Promise<UserListResponse> {
        try {
            const response = await axios.get(`${API_URL}/api/v1/admin/users/pending`);
            return response.data;
        } catch (error) {
            console.error('Failed to fetch pending users:', error);
            throw error;
        }
    },

    /**
     * Get all users with optional pending filter
     */
    async getAllUsers(includePending = false): Promise<UserListResponse> {
        try {
            const response = await axios.get(`${API_URL}/api/v1/admin/users`, {
                params: { include_pending: includePending }
            });
            return response.data;
        } catch (error) {
            console.error('Failed to fetch users:', error);
            throw error;
        }
    },

    /**
     * Approve a pending user
     */
    async approveUser(userId: number): Promise<{ success: boolean; message: string }> {
        try {
            const response = await axios.post(`${API_URL}/api/v1/admin/users/${userId}/approve`);
            return response.data;
        } catch (error) {
            console.error('Failed to approve user:', error);
            throw error;
        }
    },

    /**
     * Reject a pending user
     */
    async rejectUser(userId: number): Promise<{ success: boolean; message: string }> {
        try {
            const response = await axios.post(`${API_URL}/api/v1/admin/users/${userId}/reject`);
            return response.data;
        } catch (error) {
            console.error('Failed to reject user:', error);
            throw error;
        }
    },

    /**
     * Delete a user
     */
    async deleteUser(userId: number): Promise<{ success: boolean; message: string }> {
        try {
            const response = await axios.delete(`${API_URL}/api/v1/admin/users/${userId}`);
            return response.data;
        } catch (error) {
            console.error('Failed to delete user:', error);
            throw error;
        }
    },

    /**
     * Admin change user password
     */
    async changeUserPassword(userId: number, newPassword: string): Promise<{ success: boolean; message: string }> {
        try {
            const response = await axios.post(
                `${API_URL}/api/v1/admin/users/${userId}/change-password`,
                { new_password: newPassword }
            );
            return response.data;
        } catch (error) {
            console.error('Failed to change password:', error);
            throw error;
        }
    }
};