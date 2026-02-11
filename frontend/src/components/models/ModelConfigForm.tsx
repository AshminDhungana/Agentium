import React, { useState, useEffect } from 'react';
import { 
    AlertCircle, 
    Check, 
    Loader2, 
    Server, 
    Key, 
    Globe, 
    Settings, 
    TestTube, 
    ChevronLeft,
    Sparkles,
    Zap,
    CheckCircle,
    XCircle,
    Download
} from 'lucide-react';
import { modelsApi } from '../../services/models';
import type { ModelConfig, ProviderInfo, ProviderType } from '../../types';

interface ModelConfigFormProps {
    initialConfig?: ModelConfig;
    onSave: (config: ModelConfig) => void;
    onCancel: () => void;
}

export const ModelConfigForm: React.FC<ModelConfigFormProps> = ({ initialConfig, onSave, onCancel }) => {
    const [step, setStep] = useState<'provider' | 'configure'>('provider');
    const [providers, setProviders] = useState<ProviderInfo[]>([]);
    const [selectedProvider, setSelectedProvider] = useState<ProviderInfo | null>(null);
    const [isUniversal, setIsUniversal] = useState(false);
    const [isLoadingProviders, setIsLoadingProviders] = useState(true);

    // Form state
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
        is_default: false
    });

    const [isLoading, setIsLoading] = useState(false);
    const [testing, setTesting] = useState(false);
    const [fetchingModels, setFetchingModels] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string; error?: string } | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Load providers on mount
    useEffect(() => {
        const loadProviders = async () => {
            setIsLoadingProviders(true);
            try {
                const data = await modelsApi.getProviders();
                console.log('Loaded providers:', data);
                if (Array.isArray(data)) {
                    setProviders(data);
                } else {
                    console.error('Providers data is not an array:', data);
                    setError('Invalid providers data received');
                }
            } catch (err: any) {
                console.error('Failed to load providers:', err);
                setError(err.message || 'Failed to load providers');
            } finally {
                setIsLoadingProviders(false);
            }
        };
        
        loadProviders();
    }, []);

    // Handle initialConfig separately
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
                is_default: initialConfig.is_default
            });
        }
    }, [initialConfig, providers]);

    const selectProvider = (provider: ProviderInfo) => {
        setSelectedProvider(provider);
        setIsUniversal(false);

        const baseUrl = provider.default_base_url || '';
        const defaultModel = provider.popular_models?.[0] || '';

        setFormData(prev => ({
            ...prev,
            provider: provider.id as ProviderType,
            api_base_url: baseUrl,
            default_model: defaultModel,
            available_models: provider.popular_models || [],
            config_name: prev.config_name || `${provider.display_name} Config`
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
            config_name: prev.config_name || 'Custom Provider'
        }));
        setStep('configure');
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value, type } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked :
                type === 'number' ? parseFloat(value) : value
        }));
    };

    // ✨ UPDATED: Direct model fetching without creating config
    const fetchAvailableModels = async () => {
        // Validate prerequisites
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
            // Call the new direct endpoint - no config creation needed!
            const result = await modelsApi.fetchModelsDirectly({
                provider: formData.provider,
                api_key: formData.api_key || undefined,
                api_base_url: formData.api_base_url || undefined,
                local_server_url: formData.local_server_url || undefined
            });

            // Update form with fetched models
            setFormData(prev => ({
                ...prev,
                available_models: result.models || [],
                // Only auto-select if user hasn't chosen one yet
                default_model: prev.default_model || result.default_recommended || result.models?.[0] || ''
            }));

            // Show success feedback
            setTestResult({
                success: true,
                message: `✓ Found ${result.count} available models from ${result.provider}`
            });

        } catch (err: any) {
            const errorMsg = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`Failed to fetch models: ${errorMsg}`);
            
            // Clear test result on error
            setTestResult({
                success: false,
                message: 'Failed to fetch models',
                error: errorMsg
            });
        } finally {
            setFetchingModels(false);
        }
    };

    const handleTestConnection = async () => {
        setTesting(true);
        setTestResult(null);
        setError(null);

        try {
            // Create temporary config for testing
            const payload: any = {
                provider: formData.provider,
                config_name: 'Test Config',
                default_model: formData.default_model,
                api_key: formData.api_key || undefined,
                max_tokens: formData.max_tokens,
                temperature: formData.temperature
            };

            if (formData.provider === 'local') {
                payload.local_server_url = formData.local_server_url;
            } else if (formData.api_base_url) {
                payload.api_base_url = formData.api_base_url;
            }

            if (isUniversal) {
                payload.provider_name = formData.custom_provider_name;
            }

            const tempConfig = await modelsApi.createConfig(payload);
            const result = await modelsApi.testConfig(tempConfig.id);
            
            setTestResult({
                success: result.success,
                message: result.success 
                    ? `✓ Connection successful! (${result.latency_ms}ms)` 
                    : '✗ Connection failed',
                error: result.error
            });

            // Clean up
            await modelsApi.deleteConfig(tempConfig.id);
            
        } catch (err: any) {
            setTestResult({
                success: false,
                message: 'Connection failed',
                error: err.response?.data?.detail || err.message
            });
        } finally {
            setTesting(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            const payload: any = {
                provider: formData.provider,
                config_name: formData.config_name,
                default_model: formData.default_model,
                available_models: formData.available_models,
                max_tokens: formData.max_tokens,
                temperature: formData.temperature,
                top_p: formData.top_p,
                timeout_seconds: formData.timeout,
                is_default: formData.is_default
            };

            if (formData.api_key) {
                payload.api_key = formData.api_key;
            }

            if (formData.provider === 'local') {
                payload.local_server_url = formData.local_server_url;
            } else if (formData.api_base_url) {
                payload.api_base_url = formData.api_base_url;
            }

            if (isUniversal || formData.provider === 'custom') {
                payload.provider_name = formData.custom_provider_name;
            }

            let result;
            if (initialConfig) {
                result = await modelsApi.updateConfig(initialConfig.id, payload);
            } else {
                result = await modelsApi.createConfig(payload);
            }

            onSave(result);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to save configuration');
        } finally {
            setIsLoading(false);
        }
    };

    const getProviderColor = (provider: string) => {
        const colors: Record<string, string> = {
            openai: 'from-emerald-500 to-teal-600',
            anthropic: 'from-orange-500 to-amber-600',
            gemini: 'from-blue-500 to-indigo-600',
            groq: 'from-purple-500 to-fuchsia-600',
            mistral: 'from-rose-500 to-pink-600',
            together: 'from-cyan-500 to-sky-600',
            moonshot: 'from-violet-500 to-purple-600',
            deepseek: 'from-red-500 to-rose-600',
            local: 'from-slate-500 to-gray-600',
            custom: 'from-yellow-500 to-orange-600',
        };
        return colors[provider] || 'from-gray-500 to-slate-600';
    };

    if (step === 'provider') {
        return (
            <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50/30 to-purple-50/20 dark:from-gray-900 dark:via-gray-900 dark:to-gray-800 p-8">
                <div className="max-w-6xl mx-auto">
                    {/* Header */}
                    <button
                        onClick={onCancel}
                        className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-6 transition-colors"
                    >
                        <ChevronLeft className="w-5 h-5" />
                        <span>Back to Configurations</span>
                    </button>

                    <div className="mb-10">
                        <h1 className="text-4xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-purple-900 dark:from-white dark:via-blue-200 dark:to-purple-200 bg-clip-text text-transparent mb-3">
                            Choose Your AI Provider
                        </h1>
                        <p className="text-gray-600 dark:text-gray-400 text-lg">
                            Select from world-class AI providers or run models locally
                        </p>
                    </div>

                    {/* Error Display */}
                    {error && (
                        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="font-medium text-red-900 dark:text-red-300">Error</p>
                                <p className="text-sm text-red-700 dark:text-red-400 mt-1">{error}</p>
                            </div>
                        </div>
                    )}

                    {/* Loading State */}
                    {isLoadingProviders ? (
                        <div className="flex items-center justify-center py-20">
                            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                            <span className="ml-3 text-gray-600 dark:text-gray-400">Loading providers...</span>
                        </div>
                    ) : (
                        /* Provider Grid */
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {providers && providers.length > 0 ? (
                                providers.filter(p => p && p.id !== 'custom').map((provider) => (
                                    <button
                                        key={provider.id}
                                        onClick={() => selectProvider(provider)}
                                        className="group relative bg-white dark:bg-gray-800 rounded-2xl p-6 border-2 border-gray-200 dark:border-gray-700 hover:border-transparent hover:shadow-2xl transition-all duration-300 text-left overflow-hidden"
                                    >
                                        {/* Gradient Border on Hover */}
                                        <div className={`absolute inset-0 bg-gradient-to-r ${getProviderColor(provider.id)} opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl -z-10`}></div>
                                        <div className="absolute inset-[2px] bg-white dark:bg-gray-800 rounded-2xl"></div>
                                        
                                        {/* Content */}
                                        <div className="relative z-10">
                                            <div className={`w-12 h-12 rounded-xl bg-gradient-to-r ${getProviderColor(provider.id)} flex items-center justify-center mb-4`}>
                                                {provider.id === 'openai' && <Sparkles className="w-6 h-6 text-white" />}
                                                {provider.id === 'groq' && <Zap className="w-6 h-6 text-white" />}
                                                {!['openai', 'groq'].includes(provider.id) && <Settings className="w-6 h-6 text-white" />}
                                            </div>
                                            
                                            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                                                {provider.display_name}
                                            </h3>
                                            
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                                                {provider.description}
                                            </p>

                                            {provider.popular_models && provider.popular_models.length > 0 && (
                                                <div className="flex flex-wrap gap-1">
                                                    {provider.popular_models.slice(0, 3).map((model, idx) => (
                                                        <span 
                                                            key={idx}
                                                            className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-xs font-mono"
                                                        >
                                                            {model?.split('/')?.pop() || model}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </button>
                                ))
                            ) : (
                                <div className="col-span-full text-center py-12 text-gray-500 dark:text-gray-400">
                                    No providers available. Please check your connection.
                                </div>
                            )}

                            {/* Custom Provider */}
                            <button
                                onClick={handleUniversalSelect}
                                className="group relative bg-gradient-to-br from-yellow-50 to-orange-50 dark:from-yellow-900/20 dark:to-orange-900/20 rounded-2xl p-6 border-2 border-yellow-200 dark:border-yellow-800 hover:border-yellow-400 dark:hover:border-yellow-600 hover:shadow-2xl transition-all duration-300 text-left"
                            >
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-r from-yellow-500 to-orange-600 flex items-center justify-center mb-4">
                                    <Globe className="w-6 h-6 text-white" />
                                </div>
                                <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                                    Custom Provider
                                </h3>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    Any OpenAI-compatible API endpoint
                                </p>
                            </button>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // Configure Step
    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50/30 to-purple-50/20 dark:from-gray-900 dark:via-gray-900 dark:to-gray-800 p-8">
            <div className="max-w-3xl mx-auto">
                {/* Header */}
                <button
                    onClick={() => setStep('provider')}
                    className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-6 transition-colors"
                >
                    <ChevronLeft className="w-5 h-5" />
                    <span>Change Provider</span>
                </button>

                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                        Configure {selectedProvider?.display_name || 'Custom Provider'}
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400">
                        Set up your API credentials and model preferences
                    </p>
                </div>

                {/* Form Card */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-xl">
                    <form onSubmit={handleSubmit} className="p-8 space-y-6">
                        {/* Error/Success Messages */}
                        {error && (
                            <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3">
                                <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="font-medium text-red-900 dark:text-red-300">Error</p>
                                    <p className="text-sm text-red-700 dark:text-red-400 mt-1">{error}</p>
                                </div>
                            </div>
                        )}

                        {testResult && (
                            <div className={`p-4 rounded-xl flex items-start gap-3 ${
                                testResult.success 
                                    ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                                    : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                            }`}>
                                {testResult.success ? (
                                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                                ) : (
                                    <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                                )}
                                <div>
                                    <p className={`font-medium ${
                                        testResult.success 
                                            ? 'text-green-900 dark:text-green-300'
                                            : 'text-red-900 dark:text-red-300'
                                    }`}>
                                        {testResult.message}
                                    </p>
                                    {testResult.error && (
                                        <p className="text-sm text-red-700 dark:text-red-400 mt-1">{testResult.error}</p>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Configuration Name */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Configuration Name <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="text"
                                name="config_name"
                                value={formData.config_name}
                                onChange={handleChange}
                                className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                                placeholder="My OpenAI Config"
                                required
                            />
                        </div>

                        {/* API Key */}
                        {selectedProvider?.requires_api_key && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                                    <Key className="w-4 h-4" />
                                    API Key <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="password"
                                    name="api_key"
                                    value={formData.api_key}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono transition-all"
                                    placeholder="sk-..."
                                    required={!initialConfig}
                                />
                                {initialConfig?.api_key_masked && !formData.api_key && (
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                        Current: {initialConfig.api_key_masked} (leave empty to keep)
                                    </p>
                                )}
                            </div>
                        )}

                        {/* Base URL */}
                        {(selectedProvider?.requires_base_url || isUniversal) && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                                    <Globe className="w-4 h-4" />
                                    API Base URL <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="text"
                                    name="api_base_url"
                                    value={formData.api_base_url}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono transition-all"
                                    placeholder="https://api.provider.com/v1 "
                                    required
                                />
                            </div>
                        )}

                        {/* Local Server URL */}
                        {formData.provider === 'local' && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                                    <Server className="w-4 h-4" />
                                    Local Server URL
                                </label>
                                <input
                                    type="text"
                                    name="local_server_url"
                                    value={formData.local_server_url}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono transition-all"
                                />
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Default: Ollama (http://localhost:11434/v1). For LM Studio use http://localhost:1234/v1
                                </p>
                            </div>
                        )}

                        {/* Model Selection - UPDATED */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Model <span className="text-red-500">*</span>
                            </label>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    name="default_model"
                                    value={formData.default_model}
                                    onChange={handleChange}
                                    className="flex-1 px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono transition-all"
                                    placeholder={isUniversal ? "model-name" : "Select or type model name"}
                                    list="available-models"
                                    required
                                />
                                {!isUniversal && formData.provider !== 'local' && (
                                    <button
                                        type="button"
                                        onClick={fetchAvailableModels}
                                        disabled={fetchingModels || (!formData.api_key && selectedProvider?.requires_api_key)}
                                        className="px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-xl font-medium transition-colors flex items-center gap-2 disabled:cursor-not-allowed whitespace-nowrap"
                                        title={!formData.api_key && selectedProvider?.requires_api_key ? "Enter API key first" : "Fetch available models from provider"}
                                    >
                                        {fetchingModels ? (
                                            <>
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                Fetching...
                                            </>
                                        ) : (
                                            <>
                                                <Download className="w-4 h-4" />
                                                Fetch Models
                                            </>
                                        )}
                                    </button>
                                )}
                                {formData.provider === 'local' && (
                                    <button
                                        type="button"
                                        onClick={fetchAvailableModels}
                                        disabled={fetchingModels}
                                        className="px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-xl font-medium transition-colors flex items-center gap-2 disabled:cursor-not-allowed whitespace-nowrap"
                                        title="Fetch installed models from local server"
                                    >
                                        {fetchingModels ? (
                                            <>
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                Fetching...
                                            </>
                                        ) : (
                                            <>
                                                <Download className="w-4 h-4" />
                                                Fetch Models
                                            </>
                                        )}
                                    </button>
                                )}
                            </div>
                            
                            <datalist id="available-models">
                                {formData.available_models.map(m => (
                                    <option key={m} value={m} />
                                ))}
                            </datalist>
                            
                            {/* Show success feedback */}
                            {formData.available_models.length > 0 && (
                                <p className="text-xs text-green-600 dark:text-green-400 mt-1 flex items-center gap-1">
                                    <Check className="w-3 h-3" />
                                    {formData.available_models.length} models available from {formData.provider}
                                </p>
                            )}
                            
                            {/* Show instructions */}
                            {formData.available_models.length === 0 && (
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    {isUniversal
                                        ? "Enter the exact model name as expected by the API"
                                        : selectedProvider?.requires_api_key && !formData.api_key
                                        ? "Enter your API key and click 'Fetch Models' to see available options"
                                        : "Click 'Fetch Models' to see available options, or type a model name manually"
                                    }
                                </p>
                            )}
                        </div>

                        {/* Advanced Settings */}
                        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-6 bg-gray-50 dark:bg-gray-900/50">
                            <h4 className="font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                <Settings className="w-4 h-4" />
                                Advanced Settings
                            </h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm text-gray-600 dark:text-gray-400 mb-2">Max Tokens</label>
                                    <input
                                        type="number"
                                        name="max_tokens"
                                        value={formData.max_tokens}
                                        onChange={handleChange}
                                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        min="100"
                                        max="128000"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm text-gray-600 dark:text-gray-400 mb-2">Temperature</label>
                                    <input
                                        type="number"
                                        name="temperature"
                                        value={formData.temperature}
                                        onChange={handleChange}
                                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        min="0"
                                        max="2"
                                        step="0.1"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Default Checkbox */}
                        <label className="flex items-center gap-3 cursor-pointer">
                            <input
                                type="checkbox"
                                name="is_default"
                                checked={formData.is_default}
                                onChange={handleChange}
                                className="w-5 h-5 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                            />
                            <span className="text-gray-700 dark:text-gray-300 font-medium">
                                Set as default configuration
                            </span>
                        </label>

                        {/* Test Connection */}
                        <button
                            type="button"
                            onClick={handleTestConnection}
                            disabled={testing || !formData.default_model}
                            className="w-full py-3 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 border-2 border-gray-300 dark:border-gray-600 rounded-xl font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {testing ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Testing Connection...
                                </>
                            ) : (
                                <>
                                    <TestTube className="w-4 h-4" />
                                    Test Connection
                                </>
                            )}
                        </button>

                        {/* Actions */}
                        <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                            <button
                                type="button"
                                onClick={onCancel}
                                className="flex-1 px-6 py-3 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-xl font-medium transition-colors"
                                disabled={isLoading}
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                className="flex-1 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                disabled={isLoading}
                            >
                                {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                                {initialConfig ? 'Update Configuration' : 'Create Configuration'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};