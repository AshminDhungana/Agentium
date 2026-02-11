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
        const response = await api.get('/api/v1/models/providers');
        return response.data;
    },

    // Get user's configurations
    getConfigs: async (): Promise<ModelConfig[]> => {
        const response = await api.get('/api/v1/models/configs');
        // Handle both array and wrapped responses
        const data = response.data;
        if (Array.isArray(data)) return data;
        if (data?.configs) return data.configs;
        return [];
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
        const response = await api.post('/api/v1/models/configs', config);
        return response.data;
    },

    // Universal endpoint for ANY OpenAI-compatible provider not in standard list
    createUniversalConfig: async (input: UniversalProviderInput): Promise<ModelConfig> => {
        const response = await api.post('/api/v1/models/configs/universal', input);
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
        const response = await api.put(`/api/v1/models/configs/${configId}`, updates);
        return response.data;
    },

    // Delete configuration
    deleteConfig: async (configId: string): Promise<void> => {
        await api.delete(`/api/v1/models/configs/${configId}`);
    },

    // Test connection
    testConfig: async (configId: string): Promise<TestResult> => {
        const response = await api.post(`/api/v1/models/configs/${configId}/test`);
        return response.data;
    },

    // Fetch available models from provider API (requires existing config)
    fetchModels: async (configId: string): Promise<{
        provider: string;
        models: string[];
        count: number;
    }> => {
        const response = await api.post(`/api/v1/models/configs/${configId}/fetch-models`);
        return response.data;
    },

    // NEW: Fetch models directly from provider WITHOUT creating a config first
    fetchModelsDirectly: async (params: {
        provider: ProviderType;
        api_key?: string;
        api_base_url?: string;
        local_server_url?: string;
    }): Promise<{
        provider: string;
        models: string[];
        count: number;
        default_recommended?: string;
    }> => {
        const response = await api.post('/api/v1/models/providers/fetch-models-direct', params);
        return response.data;
    },

    // Set as default
    setDefault: async (configId: string): Promise<void> => {
        await api.post(`/api/v1/models/configs/${configId}/set-default`);
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
        const response = await api.get(`/api/v1/models/configs/${configId}/usage?days=${days}`);
        return response.data;
    }
};

export default modelsApi;