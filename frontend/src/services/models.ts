import { api } from './api';
import type {
    ModelConfig,
    ProviderInfo,
    TestResult,
    UniversalProviderInput,
    ProviderType
} from '../types';

export const modelsApi = {
    // Get all available providers with metadata
    getProviders: async (): Promise<ProviderInfo[]> => {
        const response = await api.get('/models/providers');
        return response.data;
    },

    // Get user's configurations
    getConfigs: async (): Promise<ModelConfig[]> => {
        const response = await api.get('/models/configs');
        return response.data;
    },

    // Create standard configuration (OpenAI, Anthropic, Groq, etc.)
    createConfig: async (config: {
        provider: ProviderType;
        config_name: string;
        api_key?: string;
        api_base_url?: string;
        local_server_url?: string;
        default_model: string;
        available_models?: string[];
        is_default?: boolean;
        max_tokens?: number;
        temperature?: number;
        top_p?: number;
        timeout_seconds?: number;
    }): Promise<ModelConfig> => {
        const response = await api.post('/models/configs', config);
        return response.data;
    },

    // Universal endpoint for ANY OpenAI-compatible provider not in standard list
    createUniversalConfig: async (input: UniversalProviderInput): Promise<ModelConfig> => {
        const response = await api.post('/models/configs/universal', input);
        return response.data;
    },

    // Update configuration
    updateConfig: async (configId: string, updates: Partial<{
        config_name: string;
        api_key?: string;
        api_base_url?: string;
        local_server_url?: string;
        default_model: string;
        available_models: string[];
        is_default: boolean;
        max_tokens: number;
        temperature: number;
        status: string;
    }>): Promise<ModelConfig> => {
        const response = await api.put(`/models/configs/${configId}`, updates);
        return response.data;
    },

    // Delete configuration
    deleteConfig: async (configId: string): Promise<void> => {
        await api.delete(`/models/configs/${configId}`);
    },

    // Test connection
    testConfig: async (configId: string): Promise<TestResult> => {
        const response = await api.post(`/models/configs/${configId}/test`);
        return response.data;
    },

    // Fetch available models from provider API (dynamic)
    fetchModels: async (configId: string): Promise<{
        provider: string;
        models: string[];
        count: number;
    }> => {
        const response = await api.post(`/models/configs/${configId}/fetch-models`);
        return response.data;
    },

    // Set as default
    setDefault: async (configId: string): Promise<void> => {
        await api.post(`/models/configs/${configId}/set-default`);
    },

    // Get usage statistics
    getUsage: async (configId: string, days: number = 7): Promise<{
        period_days: number;
        total_tokens: number;
        total_requests: number;
        total_cost_usd: number;
        success_rate: number;
        daily_breakdown: Record<string, { tokens: number; requests: number; cost: number }>;
    }> => {
        const response = await api.get(`/models/configs/${configId}/usage?days=${days}`);
        return response.data;
    }
};

export default modelsApi;