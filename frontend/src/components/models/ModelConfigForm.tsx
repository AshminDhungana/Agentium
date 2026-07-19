/**
 * @description Form for adding or editing AI provider model configurations.
 * Supports all provider types with provider-specific fields and validation.
 * @example
 * ```tsx
 * import { ModelConfigForm } from '@/components/models/ModelConfigForm';
 *
 * <ModelConfigForm onSubmit={handleSubmit} onCancel={handleCancel} />
 * ```
 * @param {(config: ModelConfig) => Promise<void>} props.onSubmit - Callback with validated configuration data.
 * @param {() => void} props.onCancel - Callback to cancel the form.
 */

import React, { useState, useEffect, useRef, useMemo, useId } from 'react';
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
    DollarSign,
} from 'lucide-react';
import { modelsApi, type PricingMap } from '@/services/models';
import { getProviderFormGradient, ProviderFormIcon } from '@/constants/providerMeta';
import { ProviderLogo } from '@/components/models/ProviderLogo';
import type { ModelConfig, ProviderInfo, ProviderType } from '@/types';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { RateLimitField } from './RateLimitField';

type Effort = 'none' | 'low' | 'medium' | 'high' | 'xhigh';

// Mirrors backend PROVIDER_THINKING in backend/services/model_provider.py.
// Controls whether the effort control is shown. The two maps MUST stay in sync
// (same provider keys + matching hints): if they drift, the UI may show the
// effort control for a model the backend refuses to gate, or vice-versa.
// When editing a hint here, update the backend copy identically (and vice-versa).
const THINKING_PROVIDERS: Record<string, RegExp | null> = {
    OPENAI: /(^|[-/])(o1|o3|o4|gpt-5)/i,
    AZURE_OPENAI: /(^|[-/])(o1|o3|o4|gpt-5)/i,
    ANTHROPIC: /claude-(opus|sonnet|haiku)[- ]?(4|4[-.]5)/i,
    GEMINI: /gemini-2\.5|gemini-3/i,
    DEEPSEEK: /reasoner|v4/i,
    GROQ: /gpt-oss|qwen|r1|qwq|reason/i,
    MISTRAL: /magistral|thinking/i,
    TOGETHER: /r1|qwq|reasoner|thinking|gpt-oss/i,
    MOONSHOT: /k2|kimi/i,
    LOCAL: /qwq|r1|deepseek|thinking|z1|qwen3/i,
    CUSTOM: /(^|[-/])(o1|o3|o4|gpt-5)|qwq|r1|reasoner|thinking|gpt-oss/i,
    // COHERE: omitted -> hidden
};

export function supportsThinking(provider: string, model: string): boolean {
    const hint = THINKING_PROVIDERS[provider?.toUpperCase()];
    if (!hint) return false;
    if (hint === null) return true;
    return hint.test(model || '');
}

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

// ─── Price line for a single model (free/unknown → suppressed) ─────────────
function ModelPriceLine({ pricingMap, modelId }: {
    pricingMap: PricingMap | null;
    modelId: string;
}) {
    if (!pricingMap || !modelId) return null;
    const price = pricingMap[modelId.toLowerCase().trim()];
    // null => free / no pricing data => show nothing.
    if (!price) return null;
    return (
        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1.5 flex items-center gap-1.5" role="status">
            <DollarSign className="w-3 h-3" aria-hidden="true" />
            <span className="font-mono">
                ${price.input_rate_per_1m.toFixed(2)} in / ${price.output_rate_per_1m.toFixed(2)} out
            </span>
            <span className="text-gray-400 dark:text-gray-500">per 1M tokens</span>
        </p>
    );
}

// ─── Searchable model picker (search box + filtered list after fetch) ─────────

function SearchableModelSelect({ models, value, onChange, inputCls }: {
    models: string[];
    value: string;
    onChange: (m: string) => void;
    inputCls: string;
}) {
    const [query, setQuery] = useState(value);
    const [open, setOpen] = useState(false);
    const [highlight, setHighlight] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);
    const listId = useId();

    // Keep the box in sync when the external value changes (e.g. after a
    // fetch auto-selects a default) and the user isn't actively searching.
    useEffect(() => {
        if (!open) setQuery(value);
    }, [value, open]);

    const filtered = useMemo(
        () => models.filter(m => m.toLowerCase().includes(query.trim().toLowerCase())),
        [models, query],
    );

    useEffect(() => {
        if (open) setHighlight(0);
    }, [query, open]);

    useEffect(() => {
        if (!open) return;
        const onDocClick = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', onDocClick);
        return () => document.removeEventListener('mousedown', onDocClick);
    }, [open]);

    const selectModel = (m: string) => {
        onChange(m);
        setQuery(m);
        setOpen(false);
    };

    const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!open) { setOpen(true); return; }
            setHighlight(i => Math.min(i + 1, filtered.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setHighlight(i => Math.max(i - 1, 0));
        } else if (e.key === 'Enter') {
            if (open && filtered[highlight]) {
                e.preventDefault();
                selectModel(filtered[highlight]);
            }
        } else if (e.key === 'Escape') {
            setOpen(false);
        }
    };

    return (
        <div ref={containerRef} className="relative flex-1">
            <input
                id="default_model"
                type="text"
                autoComplete="off"
                role="combobox"
                aria-expanded={open}
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={open && filtered[highlight] ? `${listId}-${highlight}` : undefined}
                value={query}
                placeholder="Search models…"
                onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
                onFocus={() => {
                    setOpen(true);
                    setQuery('');
                    const idx = models.indexOf(value);
                    setHighlight(idx >= 0 ? idx : 0);
                }}
                onBlur={() => setOpen(false)}
                onKeyDown={onKeyDown}
                className={`${inputCls} w-full font-mono`}
                required
                aria-required="true"
            />
            {open && (
                <ul
                    id={listId}
                    role="listbox"
                    aria-label="Available models"
                    className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#0b0e14] shadow-lg py-1"
                >
                    {filtered.length === 0 ? (
                        <li className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">No models match</li>
                    ) : (
                        filtered.map((m, i) => (
                            <li
                                key={m}
                                id={`${listId}-${i}`}
                                role="option"
                                aria-selected={m === value}
                                onMouseDown={(e) => { e.preventDefault(); selectModel(m); }}
                                onMouseEnter={() => setHighlight(i)}
                                className={`px-3 py-2 text-sm font-mono cursor-pointer ${i === highlight ? 'bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'} ${m === value ? 'font-semibold' : ''}`}
                            >
                                {m}
                            </li>
                        ))
                    )}
                </ul>
            )}
        </div>
    );
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
        requests_per_minute: 60,
        effort: 'none' as Effort,
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
    // Live, provider-sourced pricing keyed by model id (lower-cased).
    // A value of `null` means the model is free / has no price → suppress.
    const [pricingMap, setPricingMap] = useState<PricingMap | null>(null);

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
                requests_per_minute: initialConfig.requests_per_minute || 60,
                effort: (initialConfig.effort || 'none') as Effort,
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

        if (type === 'number') {
            // FIX: parseFloat('') is NaN. Writing NaN into formData silently corrupts
            // max_tokens/temperature (it then gets sent to the API or fails validation
            // with no clear cause). If the field is mid-edit (empty or not yet a valid
            // number, e.g. "0." while typing "0.7"), skip the update and keep the last
            // valid value instead of storing NaN.
            const parsed = parseFloat(value);
            if (value === '' || Number.isNaN(parsed)) return;
            setFormData(prev => ({ ...prev, [name]: parsed }));
            return;
        }

        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value,
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
        // FIX: 'local' doesn't need an API key, but it does need a server URL.
        // Without this guard, clearing the field and hitting Fetch silently
        // tries to reach an empty URL.
        if (formData.provider === 'local' && !formData.local_server_url.trim()) {
            setError('Local server URL is required to fetch models');
            return;
        }
        // Custom providers need a base URL to know where to call /models.
        if (isUniversal && !formData.api_base_url.trim()) {
            setError('API Base URL is required to fetch models from a custom provider');
            return;
        }

        setFetchingModels(true);
        setError(null);
        setTestResult(null);
        try {
            // FIX: custom/universal providers set formData.provider = 'custom', but the
            // backend's fetch-models-direct endpoint routes by ProviderType and has no
            // handler for 'custom' — it either throws or returns [], which triggers a 404
            // that crashes the error boundary and blanks the page.
            // Custom providers are always OpenAI-compatible, so send provider='openai'
            // with the custom api_base_url; the backend will call GET /models against
            // that URL exactly as it would for a real OpenAI endpoint.
            const fetchProvider = isUniversal ? 'openai' : formData.provider;

            const result = await modelsApi.fetchModelsDirectly({
                provider: fetchProvider as typeof formData.provider,
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
            // Live, provider-sourced pricing (free models map to null → suppressed).
            setPricingMap((result.pricing as PricingMap) ?? null);
            setTestResult({
                success: true,
                // FIX: String() coerce — result.provider comes from the API and could be
                // a non-string on unexpected responses, which would cause React error #31.
                message: `✓ Found ${result.count} available models from ${String(result.provider)}`,
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
                // FIX: previously omitted — a "successful" test was validating a
                // config with default top_p/timeout, not the actual values about
                // to be saved.
                top_p: formData.top_p,
                timeout_seconds: formData.timeout,
                requests_per_minute: formData.requests_per_minute,
                effort: formData.effort,
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
        // Bail before any network call — the backend rejects these with an
        // opaque 422 that previously crashed the view (React #31). Surface a
        // clear, human-readable message instead.
        if (hasBlockingValidationErrors) {
            const missing: string[] = [];
            if (configNameMissing) missing.push('Configuration Name');
            if (modelMissing) missing.push('Model');
            if (providerNameMissing) missing.push('Provider Name');
            if (apiKeyMissing) missing.push('API Key');
            setError(`Please fill in the required field(s): ${missing.join(', ')}`);
            setIsLoading(false);
            return;
        }
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
                requests_per_minute: formData.requests_per_minute,
                effort: formData.effort,
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

    // A real API key is required to actually generate (chat) for every provider
    // except LOCAL. Custom/OpenAI-compatible endpoints in particular fail later
    // with a confusing 401 if saved without a key, so block Create/Save up front.
    const apiKeyRequired = isUniversal ||
        formData.provider === 'custom' ||
        (selectedProvider?.requires_api_key ?? false);
    const apiKeyMissing = apiKeyRequired && !formData.api_key?.trim();

    const showEffort = supportsThinking(formData.provider, formData.default_model);

    // Required-field validation. The backend rejects an empty `default_model`
    // (and `config_name`), but that round-trip used to surface as a raw server
    // error and crash the view (React #31). Block submission up front instead so
    // the user can never "confirm" an incomplete form — the Create/Update button
    // is disabled and handleSubmit bails out with a friendly message.
    const configNameMissing = !formData.config_name.trim();
    const modelMissing = !formData.default_model.trim();
    const providerNameMissing = isUniversal && !formData.custom_provider_name.trim();
    const hasBlockingValidationErrors =
        apiKeyMissing || configNameMissing || modelMissing || providerNameMissing;

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
                        className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-8 transition-colors duration-150 group"
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
                        <p className="text-gray-600 dark:text-gray-400 text-sm">
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
                            <span className="ml-3 text-sm text-gray-600 dark:text-gray-400">Loading providers…</span>
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
                                                <ProviderLogo provider={provider.id} className="w-6 h-6" />
                                            </div>

                                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                                                {provider.display_name}
                                            </h3>
                                            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3 leading-relaxed">
                                                {provider.description}
                                            </p>

                                            {provider.popular_models && provider.popular_models.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5" role="list" aria-label={`Popular models for ${provider.display_name}`}>
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
                                <div className="col-span-full text-center py-16 text-sm text-gray-600 dark:text-gray-400">
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
                                <p className="text-xs text-gray-600 dark:text-gray-400">
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
                    className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white mb-8 transition-colors duration-150 group"
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
                            <ProviderLogo provider={selectedProvider?.id || 'custom'} className="w-6 h-6" />
                        </div>
                    )}
                    <div>
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                            Configure {selectedProvider?.display_name || 'Custom Provider'}
                        </h1>
                        <p className="text-gray-600 dark:text-gray-400 text-sm">
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
                                Configuration Name <span className="text-red-600" aria-hidden="true">*</span>
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
                                    Provider Name <span className="text-red-600" aria-hidden="true">*</span>
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
                        {(selectedProvider?.requires_api_key || isUniversal || formData.provider === 'custom') && (
                            <div>
                                <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 flex items-center gap-2">
                                    <Key className="w-4 h-4" aria-hidden="true" />
                                    API Key <span className="text-red-600" aria-hidden="true">*</span>
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
                                    <p className="text-xs text-gray-600 dark:text-gray-500 mt-1.5">
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
                                    API Base URL <span className="text-red-600" aria-hidden="true">*</span>
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
                                <p className="text-xs text-gray-600 dark:text-gray-500 mt-1.5">
                                    Default: Ollama (http://localhost:11434/v1). For LM Studio use http://localhost:1234/v1
                                </p>
                            </div>
                        )}

                        {/* Rate limit (requests per minute) */}
                        <RateLimitField
                            value={formData.requests_per_minute}
                            onChange={(v) => setFormData(prev => ({ ...prev, requests_per_minute: v }))}
                        />

                        {/* Model Selection */}
                        <div>
                            <label htmlFor="default_model" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Model <span className="text-red-600" aria-hidden="true">*</span>
                            </label>
                            <div className="flex gap-2">
                                {formData.available_models.length > 0 ? (
                                    <SearchableModelSelect
                                        models={formData.available_models}
                                        value={formData.default_model}
                                        onChange={(m) => setFormData(prev => ({ ...prev, default_model: m }))}
                                        inputCls={inputCls}
                                    />
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

                                {/* Fetch Models button — shown for all known providers, local,
                                    and custom providers that have a base URL configured */}
                                {(formData.provider === 'local' || !isUniversal || formData.api_base_url.trim()) && (
                                    <button
                                        type="button"
                                        onClick={fetchAvailableModels}
                                        disabled={
                                            fetchingModels
                                            || (!formData.api_key && selectedProvider?.requires_api_key === true)
                                            || (isUniversal && !formData.api_base_url.trim())
                                        }
                                        aria-label={
                                            formData.provider === 'local'
                                                ? 'Fetch installed models from local server'
                                                : 'Fetch available models from provider'
                                        }
                                        title={
                                            isUniversal && !formData.api_base_url.trim()
                                                ? 'Enter API Base URL first'
                                                : !formData.api_key && selectedProvider?.requires_api_key
                                                    ? 'Enter API key first'
                                                    : formData.provider === 'local'
                                                        ? 'Fetch installed models from local server'
                                                        : 'Fetch available models from provider'
                                        }
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
                                <>
                                    <p className="text-xs text-green-600 dark:text-green-400 mt-1.5 flex items-center gap-1" role="status">
                                        <Check className="w-3 h-3" aria-hidden="true" />
                                        {formData.available_models.length} models available from {formData.provider}
                                    </p>
                                    <ModelPriceLine
                                        pricingMap={pricingMap}
                                        modelId={formData.default_model}
                                    />
                                </>
                            ) : (
                                <p className="text-xs text-gray-600 dark:text-gray-500 mt-1.5">
                                    {isUniversal
                                        ? formData.api_base_url.trim()
                                            ? "Click 'Fetch' to discover available models, or type a model name manually"
                                            : 'Enter the API Base URL above, then click Fetch — or type the exact model name'
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
                                <Settings className="w-4 h-4 text-gray-600 dark:text-gray-400" aria-hidden="true" />
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

                            {showEffort && (
                                <div className="col-span-2">
                                    <label htmlFor="effort" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                                        Reasoning Effort
                                    </label>
                                    <select
                                        id="effort"
                                        name="effort"
                                        value={formData.effort}
                                        onChange={handleChange}
                                        className={inputCls}
                                    >
                                        <option value="none">None (disabled)</option>
                                        <option value="low">Low</option>
                                        <option value="medium">Medium</option>
                                        <option value="high">High</option>
                                        <option value="xhigh">X-High</option>
                                    </select>
                                </div>
                            )}
                        </div>

                        {/* Default checkbox */}
                        <label htmlFor="is_default" className="flex items-center gap-3 cursor-pointer group">
                            <input
                                id="is_default"
                                type="checkbox"
                                name="is_default"
                                checked={formData.is_default}
                                onChange={handleChange}
                                className="w-4 h-4 rounded border-gray-500 dark:border-[#2a3347] text-blue-600 focus:ring-blue-500 bg-white dark:bg-[#0f1117]"
                            />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors duration-150">
                                Set as default configuration
                            </span>
                        </label>

                        {/* Test Connection */}
                        <button
                            type="button"
                            onClick={handleTestConnection}
                            disabled={testing || !formData.default_model || apiKeyMissing}
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
                                disabled={isLoading || hasBlockingValidationErrors}
                                aria-label={initialConfig ? 'Update configuration' : 'Create configuration'}
                                className="flex-1 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-sm"
                            >
                                {isLoading && <LoadingSpinner size="sm" />}
                                {initialConfig ? 'Update Configuration' : 'Create Configuration'}
                            </button>
                        </div>

                        {apiKeyMissing && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                                An API key is required to create this configuration. Enter it above.
                            </p>
                        )}

                        {!apiKeyMissing && hasBlockingValidationErrors && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                                Fill in all required fields
                                {configNameMissing ? ' — Configuration Name' : ''}
                                {modelMissing ? ' — Model' : ''}
                                {providerNameMissing ? ' — Provider Name' : ''}
                                {' '}before creating this configuration.
                            </p>
                        )}
                    </form>
                </div>
            </div>
        </div>
    );
};