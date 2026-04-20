/**
 * frontend/src/components/models/ModelConfigForm.tsx
 */

import React, { useState, useEffect } from 'react';
import {
    AlertCircle,
    Check,
    Server,
    Key,
    Globe,
    Settings,
    TestTube,
    ChevronLeft,
    CheckCircle,
    XCircle,
    Download,
} from 'lucide-react';
import { modelsApi } from '@/services/models';
import { getProviderFormGradient, ProviderFormIcon } from '@/constants/providerMeta';
import type { ModelConfig, ProviderInfo, ProviderType } from '@/types';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Error helper ─────────────────────────────────────────────────────────────
//
// getErrorMessage from @/utils/errors doesn't handle Pydantic 422 responses,
// which look like: { detail: [{type, loc, msg, input, ctx}, ...] }
// If that object (or the array) reaches JSX it triggers React error #31 and
// the page goes dark. This helper always returns a plain string.

function extractErrorMessage(err: unknown): string {
    if (err && typeof err === 'object') {
        const e = err as Record<string, unknown>;

        // Axios error — dig into response body
        const data = (e?.response as Record<string, unknown> | undefined)?.data as
            | Record<string, unknown>
            | undefined;

        if (data) {
            const detail = data.detail;

            // Pydantic validation error — array of {type, loc, msg, input, ctx}
            if (Array.isArray(detail) && detail.length > 0) {
                return detail
                    .map((d: unknown) => {
                        if (d && typeof d === 'object') {
                            const item = d as Record<string, unknown>;
                            // e.g. "body → api_key: Field required"
                            const loc = Array.isArray(item.loc)
                                ? (item.loc as unknown[]).slice(1).join(' → ')
                                : '';
                            const msg = typeof item.msg === 'string' ? item.msg : JSON.stringify(item);
                            return loc ? `${loc}: ${msg}` : msg;
                        }
                        return String(d);
                    })
                    .join('; ');
            }

            // Plain string detail
            if (typeof detail === 'string') return detail;

            // Other body-level message keys
            const bodyMsg = data.message ?? data.error ?? data.msg;
            if (bodyMsg) return String(bodyMsg);
        }

        // Standard Error .message
        const msg = (err as Error).message;
        if (msg) return msg;
    }

    if (typeof err === 'string') return err;
    return 'An unexpected error occurred';
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface ModelConfigFormProps {
    initialConfig?: ModelConfig;
    onSave: (config: ModelConfig) => void;
    onCancel: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export const ModelConfigForm: React.FC<ModelConfigFormProps> = ({
    initialConfig,
    onSave,
    onCancel,
}) => {
    const [step, setStep] = useState<'provider' | 'configure'>('provider');
    const [providers, setProviders] = useState<ProviderInfo[]>([]);
    const [selectedProvider, setSelectedProvider] = useState<ProviderInfo | null>(null);
    const [isUniversal, setIsUniversal] = useState(false);
    const [isLoadingProviders, setIsLoadingProviders] = useState(true);

    const [formData, setFormData] = useState({
        config_name: '',
        provider: '' as ProviderType,
        custom_provider_name: '',
        api_key: '',
        api_base_url: '',
        local_server_url: 'http://localhost:11434/v1',
        default_model: '',
        available_models: [] as string[],
        temperature: 0.7,
        max_tokens: 4000,
        top_p: 0.9,
        timeout: 60,
        is_default: false,
    });

    const [isLoading, setIsLoading] = useState(false);
    const [testing, setTesting] = useState(false);
    const [fetchingModels, setFetchingModels] = useState(false);
    const [testResult, setTestResult] = useState<{
        success: boolean;
        message: string;
        error?: string;
    } | null>(null);
    const [error, setError] = useState<string | null>(null);

    // ── Load providers on mount ────────────────────────────────────────────

    useEffect(() => {
        const loadProviders = async () => {
            setIsLoadingProviders(true);
            try {
                const data = await modelsApi.getProviders();
                if (Array.isArray(data)) {
                    setProviders(data);
                } else {
                    setError('Invalid providers data received');
                }
            } catch (err: unknown) {
                // FIX: use extractErrorMessage so a Pydantic error object is never stored in state
                setError(extractErrorMessage(err) || 'Failed to load providers');
            } finally {
                setIsLoadingProviders(false);
            }
        };
        loadProviders();
    }, []);

    // ── Pre-populate form when editing an existing config ─────────────────

    useEffect(() => {
        if (initialConfig && providers.length > 0) {
            setStep('configure');
            const provider = providers.find(p => p.id === initialConfig.provider);
            setSelectedProvider(provider || null);
            setIsUniversal(initialConfig.provider === 'custom');
            setFormData({
                config_name: initialConfig.config_name,
                provider: initialConfig.provider,
                custom_provider_name: initialConfig.provider_name || '',
                api_key: '',
                api_base_url: initialConfig.api_base_url || '',
                local_server_url: initialConfig.local_server_url || 'http://localhost:11434/v1',
                default_model: initialConfig.default_model,
                available_models: initialConfig.available_models || [],
                temperature: initialConfig.settings?.temperature ?? 0.7,
                max_tokens: initialConfig.settings?.max_tokens ?? 4000,
                top_p: initialConfig.settings?.top_p ?? 0.9,
                timeout: initialConfig.settings?.timeout ?? 60,
                is_default: initialConfig.is_default,
            });
        }
    }, [initialConfig, providers]);

    // ── Handlers ──────────────────────────────────────────────────────────

    const selectProvider = (provider: ProviderInfo) => {
        setSelectedProvider(provider);
        setIsUniversal(false);
        setFormData(prev => ({
            ...prev,
            provider: provider.id as ProviderType,
            api_base_url: provider.default_base_url || '',
            default_model: provider.popular_models?.[0] || '',
            available_models: provider.popular_models || [],
            config_name: prev.config_name || `${provider.display_name} Config`,
        }));
        setStep('configure');
    };

    const handleUniversalSelect = () => {
        setIsUniversal(true);
        setSelectedProvider(null);
        setFormData(prev => ({
            ...prev,
            provider: 'custom' as ProviderType,
            api_base_url: '',
            default_model: '',
            config_name: prev.config_name || 'Custom Provider',
        }));
        setStep('configure');
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value, type } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox'
                ? (e.target as HTMLInputElement).checked
                : type === 'number'
                    ? parseFloat(value)
                    : value,
        }));
    };

    const fetchAvailableModels = async () => {
        if (!formData.provider) {
            setError('Please select a provider first');
            return;
        }
        if (selectedProvider?.requires_api_key && !formData.api_key) {
            setError('API key required to fetch models');
            return;
        }

        setFetchingModels(true);
        setError(null);
        setTestResult(null);
        try {
            const result = await modelsApi.fetchModelsDirectly({
                provider: formData.provider,
                api_key: formData.api_key || undefined,
                api_base_url: formData.api_base_url || undefined,
                local_server_url: formData.local_server_url || undefined,
            });
            setFormData(prev => ({
                ...prev,
                available_models: result.models || [],
                default_model: prev.default_model
                    || result.default_recommended
                    || result.models?.[0]
                    || '',
            }));
            setTestResult({
                success: true,
                message: `✓ Found ${result.count} available models from ${result.provider}`,
            });
        } catch (err: unknown) {
            // FIX: extractErrorMessage always returns a string — never an object
            const msg = extractErrorMessage(err);
            setError(`Failed to fetch models: ${msg}`);
            setTestResult({ success: false, message: 'Failed to fetch models', error: msg });
        } finally {
            setFetchingModels(false);
        }
    };

    const handleTestConnection = async () => {
        setTesting(true);
        setTestResult(null);
        setError(null);

        // FIX: track the temp config ID outside try so finally can always clean it up.
        // Previously deleteConfig was INSIDE the try block — if testConfig() threw
        // (e.g. bad API key rejected by the provider), deleteConfig was never called
        // and a ghost record was left in the database.
        let tempConfigId: string | null = null;

        try {
            const payload: Parameters<typeof modelsApi.createConfig>[0] = {
                provider: formData.provider,
                config_name: '__test_connection__',
                default_model: formData.default_model,
                api_key: formData.api_key || undefined,
                max_tokens: formData.max_tokens,
                temperature: formData.temperature,
                ...(formData.provider === 'local'
                    ? { local_server_url: formData.local_server_url }
                    : formData.api_base_url
                        ? { api_base_url: formData.api_base_url }
                        : {}),
                ...(isUniversal ? { provider_name: formData.custom_provider_name } : {}),
            };

            const tempConfig = await modelsApi.createConfig(payload);
            tempConfigId = tempConfig.id;

            const result = await modelsApi.testConfig(tempConfig.id);
            setTestResult({
                success: result.success,
                message: result.success
                    ? `✓ Connection successful! (${result.latency_ms}ms)`
                    : '✗ Connection failed',
                // FIX: coerce result.error to string — the API may return an object
                error: result.error ? String(result.error) : undefined,
            });
        } catch (err: unknown) {
            setTestResult({
                success: false,
                message: 'Connection failed',
                // FIX: extractErrorMessage — if the 422 detail is an object array,
                // this converts it to a readable string instead of storing the object.
                // Storing an object then rendering {testResult.error} was the root
                // cause of React error #31 and the page going dark.
                error: extractErrorMessage(err),
            });
        } finally {
            // FIX: always delete the temp config, even when testConfig() threw
            if (tempConfigId) {
                try {
                    await modelsApi.deleteConfig(tempConfigId);
                } catch {
                    // Best-effort cleanup — don't surface this to the user
                }
            }
            setTesting(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        try {
            const base = {
                provider: formData.provider,
                config_name: formData.config_name,
                default_model: formData.default_model,
                available_models: formData.available_models,
                max_tokens: formData.max_tokens,
                temperature: formData.temperature,
                top_p: formData.top_p,
                timeout_seconds: formData.timeout,
                is_default: formData.is_default,
                ...(formData.api_key ? { api_key: formData.api_key } : {}),
                ...(formData.provider === 'local'
                    ? { local_server_url: formData.local_server_url }
                    : formData.api_base_url
                        ? { api_base_url: formData.api_base_url }
                        : {}),
                ...((isUniversal || formData.provider === 'custom')
                    ? { provider_name: formData.custom_provider_name }
                    : {}),
            };

            const result = initialConfig
                ? await modelsApi.updateConfig(initialConfig.id, base)
                : await modelsApi.createConfig(base);

            onSave(result);
        } catch (err: unknown) {
            // FIX: extractErrorMessage — handles Pydantic 422 validation errors
            setError(extractErrorMessage(err) || 'Failed to save configuration');
        } finally {
            setIsLoading(false);
        }
    };

    /* ── Shared input class ───────────────────────────────────────────────── */
    const inputCls = 'w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150';

    /* ══════════════════════════════════════════════════════════════════════
       STEP 1 — Provider selection
    ══════════════════════════════════════════════════════════════════════ */
    if (step === 'provider') {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 md:p-8 transition-colors duration-200">
                <div className="max-w-6xl mx-auto">

                    {/* Back */}
                    <button
                        onClick={onCancel}
                        className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-8 transition-colors duration-150 group"
                        aria-label="Back to configurations"
                    >
                        <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform duration-150" aria-hidden="true" />
                        Back to Configurations
                    </button>

                    {/* Header */}
                    <div className="mb-10">
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                            Choose Your AI Provider
                        </h1>
                        <p className="text-gray-500 dark:text-gray-400 text-sm">
                            Select from world-class AI providers or run models locally.
                        </p>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-start gap-3" role="alert">
                            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                            <div>
                                <p className="text-sm font-medium text-red-900 dark:text-red-300">Error</p>
                                <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">{error}</p>
                            </div>
                        </div>
                    )}

                    {/* Provider grid */}
                    {isLoadingProviders ? (
                        <div className="flex items-center justify-center py-24" aria-live="polite" aria-busy="true">
                            <LoadingSpinner size="md" />
                            <span className="ml-3 text-sm text-gray-500 dark:text-gray-400">Loading providers…</span>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                            {providers && providers.length > 0 ? (
                                providers
                                    .filter(p => {
                                        if (!p) return false;
                                        const nid = (p.id || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                                        return !nid.includes('custom') && !nid.includes('universal');
                                    })
                                    .map((provider) => (
                                        <button
                                            key={provider.id}
                                            onClick={() => selectProvider(provider)}
                                            data-provider-id={provider.id}
                                            aria-label={`Select ${provider.display_name}`}
                                            className="group relative bg-white dark:bg-[#161b27] rounded-xl p-5 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150 text-left overflow-hidden"
                                        >
                                            {/* Hover glow */}
                                            <div
                                                className={`absolute inset-0 bg-gradient-to-br ${getProviderFormGradient(provider.id)} opacity-0 group-hover:opacity-[0.04] transition-opacity duration-300 pointer-events-none`}
                                                aria-hidden="true"
                                            />

                                            {/* Provider icon */}
                                            <div
                                                className={`w-11 h-11 rounded-lg bg-gradient-to-br ${getProviderFormGradient(provider.id)} flex items-center justify-center mb-4 shadow-lg`}
                                                aria-hidden="true"
                                            >
                                                <ProviderFormIcon providerId={provider.id} />
                                            </div>

                                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                                                {provider.display_name}
                                            </h3>
                                            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 leading-relaxed">
                                                {provider.description}
                                            </p>

                                            {provider.popular_models && provider.popular_models.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5" aria-label={`Popular models for ${provider.display_name}`}>
                                                    {provider.popular_models.slice(0, 3).map((model, idx) => (
                                                        <span
                                                            key={idx}
                                                            className="px-2 py-0.5 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] text-gray-600 dark:text-gray-400 rounded-md text-xs font-mono"
                                                        >
                                                            {model?.split('/')?.pop() || model}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </button>
                                    ))
                            ) : (
                                <div className="col-span-full text-center py-16 text-sm text-gray-500 dark:text-gray-400">
                                    No providers available. Please check your connection.
                                </div>
                            )}

                            {/* Custom Provider card */}
                            <button
                                onClick={handleUniversalSelect}
                                aria-label="Select custom OpenAI-compatible provider"
                                className="group bg-white dark:bg-[#161b27] rounded-xl p-5 border border-gray-200 dark:border-[#1e2535] hover:border-yellow-300 dark:hover:border-yellow-500/30 hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150 text-left overflow-hidden relative"
                            >
                                <div className="absolute inset-0 bg-gradient-to-br from-yellow-500 to-orange-600 opacity-0 group-hover:opacity-[0.04] transition-opacity duration-300 pointer-events-none" aria-hidden="true" />
                                <div className="w-11 h-11 rounded-lg bg-gradient-to-br from-yellow-500 to-orange-600 flex items-center justify-center mb-4" aria-hidden="true">
                                    <Globe className="w-5 h-5 text-white" />
                                </div>
                                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                                    Custom Provider
                                </h3>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    Any OpenAI-compatible API endpoint
                                </p>
                            </button>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    /* ══════════════════════════════════════════════════════════════════════
       STEP 2 — Configure
    ══════════════════════════════════════════════════════════════════════ */
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 md:p-8 transition-colors duration-200">
            <div className="max-w-3xl mx-auto">

                {/* Back */}
                <button
                    onClick={() => setStep('provider')}
                    aria-label="Back to provider selection"
                    className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-8 transition-colors duration-150 group"
                >
                    <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform duration-150" aria-hidden="true" />
                    Change Provider
                </button>

                {/* Header */}
                <div className="mb-8 flex items-center gap-4">
                    {(selectedProvider || isUniversal) && (
                        <div
                            className={`w-12 h-12 rounded-xl bg-gradient-to-br ${getProviderFormGradient(selectedProvider?.id || 'custom')} flex items-center justify-center shadow-lg flex-shrink-0`}
                            aria-hidden="true"
                        >
                            <ProviderFormIcon providerId={selectedProvider?.id || 'custom'} />
                        </div>
                    )}
                    <div>
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                            Configure {selectedProvider?.display_name || 'Custom Provider'}
                        </h1>
                        <p className="text-gray-500 dark:text-gray-400 text-sm">
                            Set up your API credentials and model preferences.
                        </p>
                    </div>
                </div>

                {/* Form card */}
                <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                    <form onSubmit={handleSubmit} className="p-6 md:p-8 space-y-6" noValidate>

                        {/* Error banner */}
                        {error && (
                            <div className="p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-start gap-3" role="alert">
                                <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                                <div>
                                    <p className="text-sm font-medium text-red-900 dark:text-red-300">Error</p>
                                    <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">{error}</p>
                                </div>
                            </div>
                        )}

                        {/* Test result banner */}
                        {testResult && (
                            <div className={`p-4 rounded-xl flex items-start gap-3 border ${testResult.success
                                    ? 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20'
                                    : 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20'
                                }`} role="status">
                                {testResult.success
                                    ? <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                                    : <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                                }
                                <div>
                                    <p className={`text-sm font-medium ${testResult.success ? 'text-green-900 dark:text-green-300' : 'text-red-900 dark:text-red-300'
                                        }`}>
                                        {testResult.message}
                                    </p>
                                    {testResult.error && (
                                        // FIX: String() coercion — final safety net so that if an object
                                        // somehow slips through, React renders "[object Object]" instead
                                        // of throwing error #31 and blanking the page.
                                        <p className="text-xs text-red-700 dark:text-red-400/80 mt-0.5">
                                            {String(testResult.error)}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Configuration Name */}
                        <div>
                            <label htmlFor="config_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Configuration Name <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="config_name"
                                type="text"
                                name="config_name"
                                value={formData.config_name}
                                onChange={handleChange}
                                className={inputCls}
                                placeholder="My OpenAI Config"
                                required
                                aria-required="true"
                            />
                        </div>

                        {/* Custom Provider Name */}
                        {isUniversal && (
                            <div>
                                <label htmlFor="custom_provider_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Provider Name <span className="text-red-500" aria-hidden="true">*</span>
                                </label>
                                <input
                                    id="custom_provider_name"
                                    type="text"
                                    name="custom_provider_name"
                                    value={formData.custom_provider_name}
                                    onChange={handleChange}
                                    className={inputCls}
                                    placeholder="e.g. My Custom LLM"
                                    required
                                    aria-required="true"
                                />
                            </div>
                        )}

                        {/* API Key */}
                        {selectedProvider?.requires_api_key && (
                            <div>
                                <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 flex items-center gap-2">
                                    <Key className="w-4 h-4" aria-hidden="true" />
                                    API Key <span className="text-red-500" aria-hidden="true">*</span>
                                </label>
                                <input
                                    id="api_key"
                                    type="password"
                                    name="api_key"
                                    value={formData.api_key}
                                    onChange={handleChange}
                                    className={`${inputCls} font-mono`}
                                    placeholder="sk-..."
                                    required={!initialConfig}
                                    aria-required={!initialConfig}
                                    autoComplete="new-password"
                                />
                                {initialConfig?.api_key_masked && !formData.api_key && (
                                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                                        Current: {initialConfig.api_key_masked} (leave empty to keep)
                                    </p>
                                )}
                            </div>
                        )}

                        {/* API Base URL */}
                        {(selectedProvider?.requires_base_url || isUniversal) && (
                            <div>
                                <label htmlFor="api_base_url" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 flex items-center gap-2">
                                    <Globe className="w-4 h-4" aria-hidden="true" />
                                    API Base URL <span className="text-red-500" aria-hidden="true">*</span>
                                </label>
                                <input
                                    id="api_base_url"
                                    type="url"
                                    name="api_base_url"
                                    value={formData.api_base_url}
                                    onChange={handleChange}
                                    className={`${inputCls} font-mono`}
                                    placeholder="https://api.provider.com/v1"
                                    required
                                    aria-required="true"
                                />
                            </div>
                        )}

                        {/* Local Server URL */}
                        {formData.provider === 'local' && (
                            <div>
                                <label htmlFor="local_server_url" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 flex items-center gap-2">
                                    <Server className="w-4 h-4" aria-hidden="true" />
                                    Local Server URL
                                </label>
                                <input
                                    id="local_server_url"
                                    type="url"
                                    name="local_server_url"
                                    value={formData.local_server_url}
                                    onChange={handleChange}
                                    className={`${inputCls} font-mono`}
                                />
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                                    Default: Ollama (http://localhost:11434/v1). For LM Studio use http://localhost:1234/v1
                                </p>
                            </div>
                        )}

                        {/* Model Selection */}
                        <div>
                            <label htmlFor="default_model" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Model <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <div className="flex gap-2">
                                {formData.available_models.length > 0 ? (
                                    <select
                                        id="default_model"
                                        name="default_model"
                                        value={formData.default_model}
                                        onChange={handleChange}
                                        className={`${inputCls} flex-1 font-mono appearance-none cursor-pointer`}
                                        required
                                        aria-required="true"
                                    >
                                        <option value="">Select a model…</option>
                                        {formData.available_models.map((m) => (
                                            <option key={m} value={m}>{m}</option>
                                        ))}
                                    </select>
                                ) : (
                                    <input
                                        id="default_model"
                                        type="text"
                                        name="default_model"
                                        value={formData.default_model}
                                        onChange={handleChange}
                                        className={`${inputCls} flex-1 font-mono`}
                                        placeholder={isUniversal ? 'model-name' : 'Select or type model name'}
                                        required
                                        aria-required="true"
                                    />
                                )}

                                {/* Fetch Models button */}
                                {(!isUniversal && formData.provider !== 'local') && (
                                    <button
                                        type="button"
                                        onClick={fetchAvailableModels}
                                        disabled={fetchingModels || (!formData.api_key && selectedProvider?.requires_api_key === true)}
                                        aria-label="Fetch available models from provider"
                                        title={!formData.api_key && selectedProvider?.requires_api_key ? 'Enter API key first' : 'Fetch available models from provider'}
                                        className="px-3 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 flex items-center gap-1.5 whitespace-nowrap shadow-sm"
                                    >
                                        {fetchingModels
                                            ? <LoadingSpinner size="sm" />
                                            : <Download className="w-4 h-4" aria-hidden="true" />
                                        }
                                        {fetchingModels ? 'Fetching…' : 'Fetch'}
                                    </button>
                                )}
                                {formData.provider === 'local' && (
                                    <button
                                        type="button"
                                        onClick={fetchAvailableModels}
                                        disabled={fetchingModels}
                                        aria-label="Fetch installed models from local server"
                                        title="Fetch installed models from local server"
                                        className="px-3 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 flex items-center gap-1.5 whitespace-nowrap shadow-sm"
                                    >
                                        {fetchingModels
                                            ? <LoadingSpinner size="sm" />
                                            : <Download className="w-4 h-4" aria-hidden="true" />
                                        }
                                        {fetchingModels ? 'Fetching…' : 'Fetch'}
                                    </button>
                                )}
                            </div>

                            {formData.available_models.length > 0 ? (
                                <p className="text-xs text-green-600 dark:text-green-400 mt-1.5 flex items-center gap-1" role="status">
                                    <Check className="w-3 h-3" aria-hidden="true" />
                                    {formData.available_models.length} models available from {formData.provider}
                                </p>
                            ) : (
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                                    {isUniversal
                                        ? 'Enter the exact model name as expected by the API'
                                        : selectedProvider?.requires_api_key && !formData.api_key
                                            ? "Enter your API key and click 'Fetch' to see available options"
                                            : "Click 'Fetch' to see available options, or type a model name manually"
                                    }
                                </p>
                            )}
                        </div>

                        {/* Advanced Settings */}
                        <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-100 dark:border-[#1e2535] rounded-xl p-5">
                            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                <Settings className="w-4 h-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
                                Advanced Settings
                            </h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="max_tokens" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                                        Max Tokens
                                    </label>
                                    <input
                                        id="max_tokens"
                                        type="number"
                                        name="max_tokens"
                                        value={formData.max_tokens}
                                        onChange={handleChange}
                                        className={inputCls}
                                        min="100"
                                        max="128000"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="temperature" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                                        Temperature
                                    </label>
                                    <input
                                        id="temperature"
                                        type="number"
                                        name="temperature"
                                        value={formData.temperature}
                                        onChange={handleChange}
                                        className={inputCls}
                                        min="0"
                                        max="2"
                                        step="0.1"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Default checkbox */}
                        <label htmlFor="is_default" className="flex items-center gap-3 cursor-pointer group">
                            <input
                                id="is_default"
                                type="checkbox"
                                name="is_default"
                                checked={formData.is_default}
                                onChange={handleChange}
                                className="w-4 h-4 rounded border-gray-300 dark:border-[#2a3347] text-blue-600 focus:ring-blue-500 bg-white dark:bg-[#0f1117]"
                            />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors duration-150">
                                Set as default configuration
                            </span>
                        </label>

                        {/* Test Connection */}
                        <button
                            type="button"
                            onClick={handleTestConnection}
                            disabled={testing || !formData.default_model}
                            aria-label="Test connection with current settings"
                            className="w-full py-2.5 bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            {testing ? (
                                <><LoadingSpinner size="sm" />Testing Connection…</>
                            ) : (
                                <><TestTube className="w-4 h-4" aria-hidden="true" />Test Connection</>
                            )}
                        </button>

                        {/* Footer actions */}
                        <div className="flex gap-3 pt-2 border-t border-gray-100 dark:border-[#1e2535]">
                            <button
                                type="button"
                                onClick={onCancel}
                                disabled={isLoading}
                                className="flex-1 px-5 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 disabled:opacity-40"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={isLoading}
                                aria-label={initialConfig ? 'Update configuration' : 'Create configuration'}
                                className="flex-1 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-sm"
                            >
                                {isLoading && <LoadingSpinner size="sm" />}
                                {initialConfig ? 'Update Configuration' : 'Create Configuration'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};