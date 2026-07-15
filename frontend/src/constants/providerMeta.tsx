/**
 * frontend/src/constants/providerMeta.tsx
 *
 * Single source of truth for all AI provider visual identity:
 *   - Card colours, backgrounds, borders, gradients  (used by ModelCard)
 *   - Provider icons for the form step               (used by ModelConfigForm)
 *   - Gradient strings for the form step             (used by ModelConfigForm)
 *
 * Previously duplicated between ModelsPage.tsx and ModelConfigForm.tsx.
 * Adding a new provider now requires editing only this file.
 */

import React from 'react';
import {
    Sparkles,
    Shield,
    TrendingUp,
    Zap,
    Cpu,
    Globe,
    Activity,
    Server,
    Settings,
    Brain,
    BrainCircuit,
    Atom,
    Wand2,
    DatabaseZap,
    Layers3,
    Network,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ProviderMeta {
    /** Human-readable name shown on the card badge */
    label: string;
    /** Tailwind text colour classes (light + dark) */
    color: string;
    /** Tailwind background classes for the icon pill */
    bg: string;
    /** Tailwind border classes for the icon pill */
    border: string;
    /** Tailwind gradient classes for the accent bar and hover glow */
    gradient: string;
    /** Icon rendered inside the card provider badge */
    cardIcon: React.ReactNode;
    /** Gradient string used in ModelConfigForm provider picker */
    formGradient: string;
}

// ─── Provider table ───────────────────────────────────────────────────────────

const PROVIDER_META: Record<string, ProviderMeta> = {
    openai: {
        label: 'OpenAI',
        color: 'text-emerald-700 dark:text-emerald-400',
        bg: 'bg-emerald-100 dark:bg-emerald-500/10',
        border: 'dark:border-emerald-500/15',
        gradient: 'from-emerald-500 to-teal-600',
        cardIcon: <Sparkles className="w-5 h-5" />,
        formGradient: 'from-emerald-400 to-teal-600',
    },
    anthropic: {
        label: 'Anthropic',
        color: 'text-orange-700 dark:text-orange-400',
        bg: 'bg-orange-100 dark:bg-orange-500/10',
        border: 'dark:border-orange-500/15',
        gradient: 'from-orange-500 to-amber-600',
        cardIcon: <Shield className="w-5 h-5" />,
        formGradient: 'from-amber-400 to-orange-600',
    },
    gemini: {
        label: 'Gemini',
        color: 'text-blue-700 dark:text-blue-400',
        bg: 'bg-blue-100 dark:bg-blue-500/10',
        border: 'dark:border-blue-500/15',
        gradient: 'from-blue-500 to-indigo-600',
        cardIcon: <TrendingUp className="w-5 h-5" />,
        formGradient: 'from-blue-400 to-violet-600',
    },
    groq: {
        label: 'Groq',
        color: 'text-purple-700 dark:text-purple-400',
        bg: 'bg-purple-100 dark:bg-purple-500/10',
        border: 'dark:border-purple-500/15',
        gradient: 'from-purple-500 to-fuchsia-600',
        cardIcon: <Zap className="w-5 h-5" />,
        formGradient: 'from-fuchsia-500 to-purple-700',
    },
    mistral: {
        label: 'Mistral',
        color: 'text-rose-700 dark:text-rose-400',
        bg: 'bg-rose-100 dark:bg-rose-500/10',
        border: 'dark:border-rose-500/15',
        gradient: 'from-rose-500 to-pink-600',
        cardIcon: <Cpu className="w-5 h-5" />,
        formGradient: 'from-sky-400 to-cyan-600',
    },
    together: {
        label: 'Together',
        color: 'text-cyan-700 dark:text-cyan-400',
        bg: 'bg-cyan-100 dark:bg-cyan-500/10',
        border: 'dark:border-cyan-500/15',
        gradient: 'from-cyan-500 to-sky-600',
        cardIcon: <Globe className="w-5 h-5" />,
        formGradient: 'from-rose-400 to-pink-600',
    },
    cohere: {
        label: 'Cohere',
        color: 'text-teal-700 dark:text-teal-400',
        bg: 'bg-teal-100 dark:bg-teal-500/10',
        border: 'dark:border-teal-500/15',
        gradient: 'from-teal-500 to-cyan-600',
        cardIcon: <Network className="w-5 h-5" />,
        formGradient: 'from-teal-400 to-cyan-600',
    },
    moonshot: {
        label: 'Moonshot',
        color: 'text-violet-700 dark:text-violet-400',
        bg: 'bg-violet-100 dark:bg-violet-500/10',
        border: 'dark:border-violet-500/15',
        gradient: 'from-violet-500 to-purple-600',
        cardIcon: <Sparkles className="w-5 h-5" />,
        formGradient: 'from-indigo-400 to-blue-700',
    },
    deepseek: {
        label: 'DeepSeek',
        color: 'text-red-700 dark:text-red-400',
        bg: 'bg-red-100 dark:bg-red-500/10',
        border: 'dark:border-red-500/15',
        gradient: 'from-red-500 to-rose-600',
        cardIcon: <Activity className="w-5 h-5" />,
        formGradient: 'from-red-400 to-rose-700',
    },
    azureopenai: {
        label: 'Azure OpenAI',
        color: 'text-sky-700 dark:text-sky-400',
        bg: 'bg-sky-100 dark:bg-sky-500/10',
        border: 'dark:border-sky-500/15',
        gradient: 'from-sky-500 to-blue-600',
        cardIcon: <Brain className="w-5 h-5" />,
        formGradient: 'from-sky-400 to-blue-600',
    },
    local: {
        label: 'Local',
        color: 'text-slate-700 dark:text-slate-400',
        bg: 'bg-slate-100 dark:bg-slate-500/10',
        border: 'dark:border-slate-500/15',
        gradient: 'from-slate-500 to-gray-600',
        cardIcon: <Server className="w-5 h-5" />,
        formGradient: 'from-slate-400 to-gray-600',
    },
    custom: {
        label: 'Custom',
        color: 'text-yellow-700 dark:text-yellow-400',
        bg: 'bg-yellow-100 dark:bg-yellow-500/10',
        border: 'dark:border-yellow-500/15',
        gradient: 'from-yellow-500 to-orange-600',
        cardIcon: <Settings className="w-5 h-5" />,
        formGradient: 'from-yellow-400 to-orange-500',
    },
};

/** Fallback metadata for any provider not in the table above. */
const FALLBACK_META: ProviderMeta = {
    label: 'Unknown',
    color: 'text-blue-700 dark:text-blue-400',
    bg: 'bg-blue-100 dark:bg-blue-500/10',
    border: 'dark:border-blue-500/15',
    gradient: 'from-blue-500 to-indigo-600',
    cardIcon: <Cpu className="w-5 h-5" />,
    formGradient: 'from-gray-500 to-slate-600',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Strips all non-alphanumeric characters and lowercases the string.
 * Used for fuzzy provider ID matching (handles 'azure_openai', 'OPENAI', etc.).
 */
export const normaliseProviderId = (id: string): string =>
    (id || '').toLowerCase().replace(/[^a-z0-9]/g, '');

/**
 * Returns the ProviderMeta record for the given provider string.
 * Falls back gracefully for unknown providers.
 */
export function getProviderMeta(provider: string): ProviderMeta {
    const id = normaliseProviderId(provider);

    if (id.includes('openai') || id.includes('gpt')) return PROVIDER_META.openai;
    if (id.includes('anthropic') || id.includes('claude')) return PROVIDER_META.anthropic;
    if (id.includes('gemini') || id.includes('google')) return PROVIDER_META.gemini;
    if (id.includes('groq')) return PROVIDER_META.groq;
    if (id.includes('mistral')) return PROVIDER_META.mistral;
    if (id.includes('together')) return PROVIDER_META.together;
    if (id.includes('cohere')) return PROVIDER_META.cohere;
    if (id.includes('moonshot') || id.includes('kimi')) return PROVIDER_META.moonshot;
    if (id.includes('deepseek')) return PROVIDER_META.deepseek;
    if (id.includes('azure')) return PROVIDER_META.azureopenai;
    if (id.includes('local') || id.includes('ollama')) return PROVIDER_META.local;
    if (id.includes('custom') || id.includes('universal')) return PROVIDER_META.custom;

    if (import.meta.env.DEV) {
        console.warn(`[providerMeta] No match for provider: "${provider}" (normalised: "${id}")`);
    }

    return { ...FALLBACK_META, label: provider || 'Unknown' };
}

/**
 * Returns only the Tailwind gradient string for the given provider.
 * Used by ModelConfigForm's provider picker cards.
 */
export function getProviderFormGradient(provider: string): string {
    return getProviderMeta(provider).formGradient;
}

/**
 * Renders the icon used inside form provider picker cards.
 * Icons are white (for use on coloured gradient backgrounds).
 */
export const ProviderFormIcon: React.FC<{
    providerId: string;
    className?: string;
}> = ({ providerId, className = 'w-5 h-5 text-white' }) => {
    const id = normaliseProviderId(providerId);

    if (id.includes('openai') || id.includes('gpt')) return <Sparkles className={className} />;
    if (id.includes('anthropic') || id.includes('claude')) return <Brain className={className} />;
    if (id.includes('gemini') || id.includes('google')) return <Atom className={className} />;
    if (id.includes('groq')) return <Zap className={className} />;
    if (id.includes('mistral')) return <BrainCircuit className={className} />;
    if (id.includes('together')) return <Layers3 className={className} />;
    if (id.includes('cohere')) return <Network className={className} />;
    if (id.includes('moonshot') || id.includes('kimi')) return <Wand2 className={className} />;
    if (id.includes('deepseek')) return <DatabaseZap className={className} />;
    if (id.includes('azure')) return <Brain className={className} />;
    if (id.includes('local') || id.includes('ollama')) return <Server className={className} />;
    if (id.includes('custom') || id.includes('universal')) return <Globe className={className} />;

    return <Cpu className={className} />;
};