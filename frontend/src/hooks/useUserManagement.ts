/**
 * useUserManagement.ts
 *
 * Custom hook that owns all state and side-effects for user management.
 * Mirrors the pattern of useModelConfigs, useMessageLog, and useDashboardData —
 * business logic lives here, Usermanagement.tsx is purely presentational.
 *
 * Improvements over the previous inline implementation:
 *  - fetchUsers wrapped in useCallback with stable onPendingCountChange ref
 *  - filteredApprovedUsers memoized with useMemo
 *  - Error state surfaced to UI (was silently swallowed)
 *  - confirmingReject / confirmingDelete use Set<string> (safe for concurrent clicks)
 *  - isChangingPassword prevents duplicate password-change submissions
 *  - handleRoleChange does an optimistic local update instead of a full refetch
 *  - roleChangeSuccess tracks per-user success indicator for 2 s visual confirmation
 *  - All action handlers use adminService (typed) instead of raw api calls
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { showToast } from '@/hooks/useToast';
import { adminService, type User } from '@/services/admin';
import { useAuthStore } from '@/store/authStore';

// ── Re-export User so consumers import from one place ─────────────────────────
export type { User };

// ── Role options shown in the dropdown ───────────────────────────────────────
export const ROLE_OPTIONS: { value: string; label: string }[] = [
    { value: 'primary_sovereign', label: 'Primary Sovereign' },
    { value: 'deputy_sovereign',  label: 'Deputy Sovereign'  },
    { value: 'observer',          label: 'Observer'           },
];

// ── Return shape ──────────────────────────────────────────────────────────────

export interface UseUserManagementReturn {
    // Data
    pendingUsers:           User[];
    approvedUsers:          User[];
    filteredApprovedUsers:  User[];
    // Status flags
    loading:                boolean;
    error:                  string | null;
    changingRole:           string | null;     // userId currently having role updated
    isChangingPassword:     boolean;
    roleChangeSuccess:      string | null;     // userId that just succeeded (2 s)
    // Confirmation sets (Set is safe for rapid multi-click)
    confirmingReject:       Set<string>;
    confirmingDelete:       Set<string>;
    // Search
    rawSearch:              string;
    searchQuery:            string;
    setRawSearch:           (v: string) => void;
    clearSearch:            () => void;
    // Actions
    fetchUsers:             () => Promise<void>;
    handleApprove:          (userId: string, username: string) => Promise<void>;
    handleReject:           (userId: string, username: string) => Promise<void>;
    handleDelete:           (userId: string, username: string) => Promise<void>;
    handleRoleChange:       (userId: string, username: string, newRole: string) => Promise<void>;
    handleChangePassword:   (userId: string, username: string, newPassword: string) => Promise<boolean>;
    toggleConfirmReject:    (userId: string) => void;
    toggleConfirmDelete:    (userId: string) => void;
    setIsChangingPassword:  (v: boolean) => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useUserManagement(
    onPendingCountChange?: (count: number) => void,
): UseUserManagementReturn {
    const { user: currentUser } = useAuthStore();

    // Store the callback in a ref so fetchUsers' useCallback never becomes stale
    // even if the parent passes a new function reference on each render.
    const onPendingCountRef = useRef(onPendingCountChange);
    useEffect(() => { onPendingCountRef.current = onPendingCountChange; }, [onPendingCountChange]);

    const [pendingUsers,  setPendingUsers]  = useState<User[]>([]);
    const [approvedUsers, setApprovedUsers] = useState<User[]>([]);
    const [loading,       setLoading]       = useState(true);
    const [error,         setError]         = useState<string | null>(null);

    // Per-row action loading states
    const [changingRole,       setChangingRole]       = useState<string | null>(null);
    const [isChangingPassword, setIsChangingPassword] = useState(false);
    const [roleChangeSuccess,  setRoleChangeSuccess]  = useState<string | null>(null);

    // Confirmation sets — Set<string> prevents a second click from overwriting
    // a pending confirmation for a different user (single-string had this bug).
    const [confirmingReject, setConfirmingReject] = useState<Set<string>>(new Set());
    const [confirmingDelete, setConfirmingDelete] = useState<Set<string>>(new Set());

    // Search with 150 ms debounce
    const [rawSearch,   setRawSearch]   = useState('');
    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        const id = setTimeout(() => setSearchQuery(rawSearch.trim()), 150);
        return () => clearTimeout(id);
    }, [rawSearch]);

    const clearSearch = useCallback(() => {
        setRawSearch('');
        setSearchQuery('');
    }, []);

    // ── filteredApprovedUsers: memoized to avoid recalculation on every render ──
    const filteredApprovedUsers = useMemo(
        () => {
            if (!searchQuery) return approvedUsers;
            const q = searchQuery.toLowerCase();
            return approvedUsers.filter(
                (u) =>
                    u.username.toLowerCase().includes(q) ||
                    u.email.toLowerCase().includes(q),
            );
        },
        [approvedUsers, searchQuery],
    );

    // ── fetchUsers: stable identity; only recreated when the callback ref changes ──
    const fetchUsers = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [pendingRes, approvedRes] = await Promise.all([
                adminService.getPendingUsers(),
                adminService.getAllUsers(),
            ]);
            const pending = pendingRes.users ?? [];
            setPendingUsers(pending);
            setApprovedUsers(approvedRes.users ?? []);
            onPendingCountRef.current?.(pending.length);
        } catch (err: any) {
            const msg = err?.response?.data?.detail ?? 'Failed to load users. Please try again.';
            setError(msg);
            showToast.error(msg);
        } finally {
            setLoading(false);
        }
    // fetchUsers intentionally has no deps — it reads callback via ref, not closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => { fetchUsers(); }, [fetchUsers]);

    // ── Confirmation toggle helpers ───────────────────────────────────────────

    const toggleConfirmReject = useCallback((userId: string) => {
        setConfirmingReject(prev => {
            const next = new Set(prev);
            next.has(userId) ? next.delete(userId) : next.add(userId);
            return next;
        });
    }, []);

    const toggleConfirmDelete = useCallback((userId: string) => {
        setConfirmingDelete(prev => {
            const next = new Set(prev);
            next.has(userId) ? next.delete(userId) : next.add(userId);
            return next;
        });
    }, []);

    // ── Action handlers ───────────────────────────────────────────────────────

    const handleApprove = useCallback(async (userId: string, username: string) => {
        try {
            await adminService.approveUser(userId);
            showToast.success(`${username} approved successfully`);
            await fetchUsers();
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to approve user');
        }
    }, [fetchUsers]);

    const handleReject = useCallback(async (userId: string, username: string) => {
        try {
            await adminService.rejectUser(userId);
            showToast.success(`${username}'s request rejected`);
            setConfirmingReject(prev => { const n = new Set(prev); n.delete(userId); return n; });
            await fetchUsers();
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to reject user');
            setConfirmingReject(prev => { const n = new Set(prev); n.delete(userId); return n; });
        }
    }, [fetchUsers]);

    const handleDelete = useCallback(async (userId: string, username: string) => {
        // Guard: cannot delete own account
        if (currentUser?.id && userId === currentUser.id) {
            showToast.error('You cannot delete your own account');
            return;
        }
        try {
            await adminService.deleteUser(userId);
            showToast.success(`${username} deleted successfully`);
            setConfirmingDelete(prev => { const n = new Set(prev); n.delete(userId); return n; });
            await fetchUsers();
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to delete user');
            setConfirmingDelete(prev => { const n = new Set(prev); n.delete(userId); return n; });
        }
    }, [fetchUsers, currentUser?.id]);

    /**
     * Role change uses an optimistic local state update on success so the
     * dropdown snaps immediately without waiting for a full re-fetch of both
     * user lists (which would be 2 extra API calls for a single field change).
     * The 2-second success indicator confirms the change to the user.
     */
    const handleRoleChange = useCallback(async (
        userId: string,
        username: string,
        newRole: string,
    ) => {
        setChangingRole(userId);
        try {
            await adminService.changeUserRole(userId, newRole);
            showToast.success(`Role updated for ${username}`);

            // Optimistic update — no full refetch needed for a single field change
            setApprovedUsers(prev =>
                prev.map(u =>
                    u.id === userId
                        ? { ...u, role: newRole, is_admin: newRole === 'primary_sovereign' }
                        : u,
                ),
            );

            // 2-second visual success indicator next to the dropdown
            setRoleChangeSuccess(userId);
            setTimeout(() => setRoleChangeSuccess(s => s === userId ? null : s), 2000);
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to update role');
        } finally {
            setChangingRole(null);
        }
    }, []);

    /**
     * Returns true on success so the modal can close itself.
     * isChangingPassword prevents duplicate submissions while in-flight.
     */
    const handleChangePassword = useCallback(async (
        userId: string,
        username: string,
        newPassword: string,
    ): Promise<boolean> => {
        setIsChangingPassword(true);
        try {
            await adminService.changeUserPassword(userId, newPassword);
            showToast.success(`Password changed for ${username}`);
            return true;
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to change password');
            return false;
        } finally {
            setIsChangingPassword(false);
        }
    }, []);

    return {
        pendingUsers,
        approvedUsers,
        filteredApprovedUsers,
        loading,
        error,
        changingRole,
        isChangingPassword,
        roleChangeSuccess,
        confirmingReject,
        confirmingDelete,
        rawSearch,
        searchQuery,
        setRawSearch,
        clearSearch,
        fetchUsers,
        handleApprove,
        handleReject,
        handleDelete,
        handleRoleChange,
        handleChangePassword,
        toggleConfirmReject,
        toggleConfirmDelete,
        setIsChangingPassword,
    };
}