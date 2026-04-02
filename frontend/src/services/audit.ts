import { api } from './api';

export interface AuditLogResult {
    success: boolean;
    message: string | null;
    error: string | null;
}

export interface AuditLogActor {
    type: string;
    id: string;
}

export interface AuditLogTarget {
    type: string;
    id: string;
}

export interface AuditLog {
    id: string;
    level: string;
    category: string;
    actor: AuditLogActor;
    action: string;
    description: string;
    target: AuditLogTarget | null;
    result: AuditLogResult;
    timestamp: string;
    metadata: any;
}

export interface AuditLogResponse {
    data: AuditLog[];
    total: number;
    skip: number;
    limit: number;
}

export const auditService = {
    getEscalations: async (skip: number = 0, limit: number = 100, search?: string) => {
        const response = await api.get<AuditLogResponse>('/audit/escalations', {
            params: { skip, limit, search }
        });
        return response.data;
    }
};