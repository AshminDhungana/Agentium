import { api } from './api';

export interface ErrorReportPayload {
    message: string;
    name: string;
    stack: string;
    component_stack: string;
    url: string;
}

export const errorReportingApi = {
    report: async (payload: ErrorReportPayload): Promise<void> => {
        await api.post('/api/v1/monitoring/frontend/errors', payload);
    },
};
