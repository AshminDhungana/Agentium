/**
 * Checkpoints Service - Frontend API for execution checkpoints.
 */

import { api } from './api';

// ============================================================================
// Types
// ============================================================================

export type CheckpointPhase = 'plan_approved' | 'execution_complete' | 'critique_passed' | 'manual';

export interface Checkpoint {
    id: string;
    agentium_id: string;
    session_id: string;
    task_id: string;
    phase: CheckpointPhase;
    branch_name: string;
    parent_checkpoint_id?: string;
    agent_states: Record<string, any>;
    artifacts: Record<string, any>;
    task_state_snapshot: Record<string, any>;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface CreateCheckpointRequest {
    task_id: string;
    phase: CheckpointPhase;
    artifacts?: Record<string, any>;
}

export interface BranchRequest {
    branch_name: string;
}

// ─── Branch comparison types ──────────────────────────────────────────────────

export type DiffStatus = 'added' | 'removed' | 'changed' | 'unchanged';

export interface FieldDiff {
    key: string;
    left: any;
    right: any;
    status: DiffStatus;
}

export interface AgentStateDiff {
    agent_id: string;
    status: DiffStatus;
    diffs: FieldDiff[];
}

export interface ArtifactDiff {
    key: string;
    status: DiffStatus;
    left: any;
    right: any;
}

export interface BranchCompareResult {
    left_branch: string;
    right_branch: string;
    left_checkpoint_id: string;
    right_checkpoint_id: string;
    left_created_at: string;
    right_created_at: string;
    task_state_diffs: FieldDiff[];
    agent_state_diffs: AgentStateDiff[];
    artifact_diffs: ArtifactDiff[];
    summary: {
        added: number;
        removed: number;
        changed: number;
        unchanged: number;
    };
}

// ============================================================================
// Phase 7: Import/Export Types
// ============================================================================

export interface CheckpointExportData {
    checkpoint: Checkpoint;
    exported_at: string;
    version: string;
    checksum: string;
}

export interface ValidationResult {
    valid: boolean;
    errors: string[];
    warnings: string[];
    checksum_valid: boolean;
    schema_version: string;
}

export interface ImportOptions {
    targetBranch?: string;
    skipValidation?: boolean;
    conflictResolution?: 'skip' | 'replace' | 'rename' | 'merge';
}

export interface ImportResult {
    success: boolean;
    checkpoint?: Checkpoint;
    conflicts?: Array<{
        type: 'id_collision' | 'branch_conflict' | 'parent_missing' | 'version_mismatch';
        message: string;
        resolution: string;
    }>;
    validation?: ValidationResult;
}

// ─── Phase 18: Unified Diff Types ───────────────────────────────────────────

export interface CheckpointDiffResult {
    left_checkpoint_id: string;
    right_checkpoint_id: string;
    left_branch?: string;
    right_branch?: string;
    left_agentium_id?: string;
    right_agentium_id?: string;
    unified_diff: string;
    left_json: string;
    right_json: string;
}

// ============================================================================
// Checkpoints Service
// ============================================================================

export const checkpointsService = {
    /**
     * Get all checkpoints, optionally filtered by session_id or task_id.
     */
    getCheckpoints: async (filters?: { session_id?: string; task_id?: string }): Promise<Checkpoint[]> => {
        const params = new URLSearchParams();
        if (filters?.session_id) params.append('session_id', filters.session_id);
        if (filters?.task_id) params.append('task_id', filters.task_id);
        const query = params.toString() ? `?${params.toString()}` : '';

        const response = await api.get<Checkpoint[]>(`/api/v1/checkpoints${query}`);
        return response.data || [];
    },

    /**
     * Get a specific checkpoint by ID.
     */
    getCheckpoint: async (checkpointId: string): Promise<Checkpoint> => {
        const response = await api.get<Checkpoint>(`/api/v1/checkpoints/${checkpointId}`);
        return response.data;
    },

    /**
     * Create a new checkpoint.
     */
    createCheckpoint: async (data: CreateCheckpointRequest): Promise<Checkpoint> => {
        const response = await api.post<Checkpoint>('/api/v1/checkpoints', data);
        return response.data;
    },

    /**
     * Resume execution from a checkpoint (time-travel).
     */
    resumeFromCheckpoint: async (checkpointId: string): Promise<any> => {
        const response = await api.post(`/api/v1/checkpoints/${checkpointId}/resume`);
        return response.data;
    },

    /**
     * Create a new branch from a checkpoint.
     */
    branchFromCheckpoint: async (checkpointId: string, branchName: string): Promise<any> => {
        const response = await api.post(`/api/v1/checkpoints/${checkpointId}/branch`, {
            branch_name: branchName,
        });
        return response.data;
    },

    /**
     * Compare two branches by diffing their latest checkpoints.
     * Returns structured diffs for task state, agent states, and artifacts.
     */
    compareBranches: async (
        leftBranch: string,
        rightBranch: string,
        taskId?: string
    ): Promise<BranchCompareResult> => {
        const params = new URLSearchParams({
            left_branch: leftBranch,
            right_branch: rightBranch,
        });
        if (taskId) params.append('task_id', taskId);
        const response = await api.get<BranchCompareResult>(
            `/api/v1/checkpoints/compare?${params.toString()}`
        );
        return response.data;
    },

    /**
     * Get a unified diff between two individual checkpoints.
     * Returns JSON snapshots and unified diff for Monaco diff viewer.
     */
    getCheckpointDiff: async (
        checkpointId: string,
        compareToId: string
    ): Promise<CheckpointDiffResult> => {
        const response = await api.get<CheckpointDiffResult>(
            `/api/v1/checkpoints/${checkpointId}/diff`,
            { params: { compare_to: compareToId } }
        );
        return response.data;
    },

    // ============================================================================
    // Phase 7: Import/Export Operations
    // ============================================================================

    /**
     * Export checkpoint as JSON file.
     */
    exportCheckpoint: async (checkpointId: string): Promise<Blob> => {
        const response = await api.get(`/api/v1/checkpoints/${checkpointId}/export`, {
            responseType: 'blob',
        });
        return response.data;
    },

    /**
     * Validate checkpoint data before import.
     */
    validateCheckpoint: async (file: File): Promise<ValidationResult> => {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await api.post<ValidationResult>('/api/v1/checkpoints/validate', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    },

    /**
     * Import checkpoint from JSON file.
     */
    importCheckpoint: async (file: File, options?: ImportOptions): Promise<ImportResult> => {
        const formData = new FormData();
        formData.append('file', file);
        
        if (options?.targetBranch) {
            formData.append('target_branch', options.targetBranch);
        }
        if (options?.skipValidation) {
            formData.append('skip_validation', 'true');
        }
        if (options?.conflictResolution) {
            formData.append('conflict_resolution', options.conflictResolution);
        }
        
        const response = await api.post<ImportResult>('/api/v1/checkpoints/import', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    },

    /**
     * Get integrity status for a checkpoint.
     */
    getCheckpointIntegrity: async (checkpointId: string): Promise<{
        valid: boolean;
        checksum: string;
        last_verified: string;
        issues: string[];
    }> => {
        const response = await api.get(`/api/v1/checkpoints/${checkpointId}/integrity`);
        return response.data;
    },

    /**
     * Verify checkpoint integrity.
     */
    verifyCheckpoint: async (checkpointId: string): Promise<{
        valid: boolean;
        checksum_match: boolean;
        issues: string[];
    }> => {
        const response = await api.post(`/api/v1/checkpoints/${checkpointId}/verify`);
        return response.data;
    },
};

// ============================================================================
// Utility Functions
// ============================================================================