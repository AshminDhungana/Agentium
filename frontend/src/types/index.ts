export interface User {
    id: string;
    username: string;
    role: 'sovereign' | 'admin';
    isAuthenticated: boolean;
}

export interface BackendStatus {
    status: 'connected' | 'disconnected' | 'connecting';
    version?: string;
    lastChecked: Date;
    latency?: number;
}

// ─── Channel core types ───────────────────────────────────────────────────────
// These were missing from the previous index.ts and were being redeclared
// locally inside ChannelsPage.tsx, causing type duplication.

export type ChannelTypeSlug =
    | 'whatsapp'
    | 'slack'
    | 'telegram'
    | 'email'
    | 'discord'
    | 'signal'
    | 'google_chat'
    | 'teams'
    | 'zalo'
    | 'matrix'
    | 'imessage'
    | 'custom';

export type ChannelStatus = 'pending' | 'active' | 'error' | 'disconnected';

export type WhatsAppProvider = 'cloud_api' | 'web_bridge';

/**
 * A configured external communication channel as returned by the backend.
 * The `config` shape is intentionally permissive — different channel types
 * populate different subsets of these optional fields.
 */
export interface Channel {
    id: string;
    name: string;
    type: ChannelTypeSlug;
    status: ChannelStatus;
    config: {
        phone_number?: string;
        has_credentials: boolean;
        webhook_url?: string;
        homeserver_url?: string;
        oa_id?: string;
        backend?: string;
        number?: string;
        bb_url?: string;
        // WhatsApp-specific
        provider?: WhatsAppProvider;
        bridge_url?: string;
        allowed_senders?: string[];
    };
    routing: {
        default_agent?: string;
        auto_create_tasks: boolean;
        require_approval: boolean;
    };
    stats: {
        received: number;
        sent: number;
        last_message?: string;
    };
}

/** Shape of the payload sent to POST /channels/ */
export interface ChannelFormData {
    name: string;
    type: ChannelTypeSlug;
    config: Record<string, string>;
    default_agent_id?: string;
    auto_create_tasks: boolean;
    require_approval: boolean;
}

// ─── Channel Metrics Types (Phase 4 + Phase 7) ───────────────────────────────

export type CircuitBreakerState = 'closed' | 'half_open' | 'open';
export type ChannelHealthStatus = 'healthy' | 'warning' | 'critical';

export interface ChannelMetrics {
    channel_id: string;
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    success_rate: number;
    circuit_breaker_state: CircuitBreakerState;
    consecutive_failures: number;
    rate_limit_hits: number;
    avg_response_time_ms?: number;
    last_failure_at?: string;
    last_rate_limit_at?: string;
    created_at: string;
    updated_at: string;
}

export interface ChannelMetricsResponse {
    channel_id: string;
    channel_name: string;
    channel_type: string;
    status: string;
    metrics: ChannelMetrics;
    health_status: ChannelHealthStatus;
}

export interface AllChannelsMetricsResponse {
    channels: ChannelMetricsResponse[];
    summary: {
        total: number;
        healthy: number;
        warning: number;
        critical: number;
        circuit_open: number;
    };
}

export interface MessageLog {
    id: string;
    channel_id: string;
    sender_id: string;
    sender_name?: string;
    content: string;
    status: 'received' | 'processing' | 'responded' | 'failed';
    error_count: number;
    last_error?: string;
    created_at: string;
    responded_at?: string;
}

// ─── Provider / Model types ───────────────────────────────────────────────────

export type ProviderType =
    | 'openai'
    | 'anthropic'
    | 'gemini'
    | 'groq'
    | 'mistral'
    | 'together'
    | 'cohere'
    | 'fireworks'
    | 'moonshot'       // Kimi 2.5
    | 'deepseek'
    | 'azure_openai'
    | 'local'          // Ollama, LM Studio
    | 'custom';        // Any OpenAI-compatible

export interface ProviderInfo {
    id: ProviderType;
    name: string;
    display_name: string;
    requires_api_key: boolean;
    requires_base_url: boolean;
    default_base_url?: string;
    description: string;
    popular_models: string[];
}

export interface ModelConfig {
    id: string;
    provider: ProviderType;
    provider_name?: string;
    config_name: string;
    default_model: string;
    available_models: string[];
    api_base_url?: string;
    local_server_url?: string;
    status: 'active' | 'inactive' | 'testing' | 'error';
    is_default: boolean;
    settings: {
        max_tokens: number;
        temperature: number;
        top_p?: number;
        timeout: number;
    };
    total_usage: {
        requests: number;
        tokens: number;
        cost_usd: number;
    };
    last_tested?: string;
    api_key_masked?: string;
}

export interface TestResult {
    success: boolean;
    message: string;
    latency_ms?: number;
    model?: string;
    tokens?: number;
    error?: string;
}

export interface UniversalProviderInput {
    provider_name: string;
    api_base_url: string;
    api_key?: string;
    default_model: string;
    config_name?: string;
    is_default?: boolean;
}

// ─── Agent / Task types ───────────────────────────────────────────────────────

export interface AgentStats {
    tasks_completed: number;
    tasks_failed: number;
    /** Optional — percentage 0–100 */
    success_rate?: number;
}

export interface Agent {
    id: string;
    agentium_id: string;
    agent_type: 'head_of_council' | 'council_member' | 'lead_agent' | 'task_agent';
    name: string;
    status: 'initializing' | 'active' | 'deliberating' | 'working' | 'suspended' | 'terminated' | 'terminating';
    model_config?: {
        config_id: string;
        config_name: string;
        provider: string;
        model: string;
    };
    parent?: string;
    subordinates: string[];
    stats: AgentStats;

    current_task_title?: string;
    current_task?: string;
    health_score?: number;
    active_task_count?: number;
    last_active_at?: string;
    idle_days?: number;
    description?: string;

    constitution_version: string;
    is_terminated: boolean;
}

export interface GovernanceInfo {
    constitutional_basis?: string | null;
    hierarchical_id?: string | null;
    parent_task_id?: string | null;
    execution_plan_id?: string | null;
    recurrence_pattern?: string | null;
    requires_deliberation: boolean;
    council_approved: boolean;
    head_approved: boolean;
}

export interface ErrorInfo {
    error_count: number;
    retry_count: number;
    max_retries: number;
    last_error?: string | null;
}

export interface DelegationInfo {
    complexity_score?: number | null;
    escalation_timeout_seconds: number;
    delegation_metadata?: Record<string, any> | null;
}

export interface Task {
    id: string;
    agentium_id?: string;
    title: string;
    description: string;
    status: string;
    priority: string;
    task_type: string;
    progress: number;
    assigned_agents: {
        head?: string | null;
        lead?: string | null;
        task_agents: string[];
    };
    governance: GovernanceInfo;
    error_info?: ErrorInfo | null;
    delegation?: DelegationInfo | null;
    created_at: string | null;
    updated_at?: string | null;
    event_count?: number;
}

// ─── Constitution types ────────────────────────────────────────────────────────

/**
 * A single article entry as normalized by the backend.
 * The backend's get_articles_dict() always returns this shape.
 * The optional `amended_at` field is provided per-article when available.
 */
export interface ConstitutionArticle {
    title: string;
    content: string;
    amended_at?: string;
}

/** A single entry in the constitution's changelog. */
export interface ConstitutionChangelogEntry {
    change: string;
    timestamp: string;
    previous_version?: string;
}

/**
 * The full constitution document as returned by GET /api/v1/constitution.
 * Matches the shape produced by Constitution.to_dict() in the backend model.
 */
export interface Constitution {
    id: string;
    version: string;
    version_number: number;
    preamble: string;
    /** Always normalized to { title, content } objects by the backend. */
    articles: Record<string, ConstitutionArticle>;
    prohibited_actions: string[];
    sovereign_preferences: Record<string, unknown>;
    effective_date: string;
    amendment_date?: string | null;
    is_active: boolean;
    is_archived?: boolean;
    created_by?: string;
    replaces_version?: string | null;
    changelog?: ConstitutionChangelogEntry[];
}

export interface AgentHealthReport {
    id: string;
    monitor: string;
    subject: string;
    status: 'healthy' | 'degraded' | 'non_responsive' | 'violation_detected' | 'termination_recommended';
    health_score: number;
    metrics: {
        success_rate: number;
        tasks_completed: number;
        avg_response_time: number;
        violations: number;
    };
    created_at: string;
}

export interface ViolationReport {
    id: string;
    reporter: string;
    violator: string;
    severity: 'minor' | 'moderate' | 'major' | 'critical';
    type: string;
    article?: string;
    description: string;
    status: string;
    action_taken?: string;
    created_at: string;
}

export interface MonitoringDashboard {
    system_health: number;
    active_alerts: number;
    agent_health_breakdown: Record<string, number>;
    recent_violations: ViolationReport[];
    latest_health_reports: AgentHealthReport[];
}

export type CheckpointPhase =
    | 'plan_approved'
    | 'execution_complete'
    | 'critique_passed'
    | 'manual';

// ─── User Preferences ─────────────────────────────────────────────────────────

export interface UserPreference {
    agentium_id: string;
    key: string;
    value: unknown;
    category: string;
    scope: string;
    data_type: string;
    editable: boolean;
    description?: string;
    last_modified_by_agent?: string;
    last_agent_modified_at?: string;
}

export interface PreferenceHistoryEntry {
    previous_value: unknown;
    new_value: unknown;
    changed_by?: string;
    change_reason?: string;
    timestamp: string;
}

export interface PreferenceCategory {
    id: string;
    name: string;
    description: string;
}

export interface SystemDefaults {
    [key: string]: unknown;
}

// ─── Dashboard aggregate types ────────────────────────────────────────────────
// Re-exported from the dedicated file so any component can import from
// the single canonical path  `@/types`  without needing to know about
// the sub-file.
export type {
    DashboardStats,
    AgentSummary,
    TaskSummary,
    DashboardSummaryResponse,
} from './dashboard';