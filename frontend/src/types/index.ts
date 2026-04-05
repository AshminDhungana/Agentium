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
        provider?: WhatsAppProvider;
        bridge_url?: string;
        allowed_senders?: string[];
        // Phase 15.3 — per-channel settings persisted in config
        rate_limit_per_minute?: number;
        rate_limit_per_hour?: number;
        content_filters?: string[];
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

export interface ChannelFormData {
    name: string;
    type: ChannelTypeSlug;
    config: Record<string, string>;
    default_agent_id?: string;
    auto_create_tasks: boolean;
    require_approval: boolean;
}

// ─── Channel Metrics Types ────────────────────────────────────────────────────

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

// ─── Phase 15.3 types ────────────────────────────────────────────────────────

/**
 * Filters accepted by GET /channels/{id}/logs and channelMetricsApi.getChannelLogs.
 */
export interface ChannelLogFilters {
    status?: 'received' | 'processing' | 'responded' | 'failed';
    /** Partial match on sender_id or sender_name */
    sender_id?: string;
    /** ISO datetime lower bound */
    date_from?: string;
    /** ISO datetime upper bound */
    date_to?: string;
    limit?: number;
    offset?: number;
}

/**
 * Body for PATCH /channels/{id}/settings.
 * All fields optional — only provided values are applied.
 */
export interface ChannelSettings {
    rate_limit_per_minute?: number;
    rate_limit_per_hour?: number;
    auto_create_tasks?: boolean;
    require_approval?: boolean;
    default_agent_id?: string;
    content_filters?: string[];
}

/**
 * Response shape of GET /channels/{id}/health (Phase 15.3 extended).
 */
export interface ChannelHealthDetail {
    channel_id: string;
    channel_name: string;
    channel_type: string;
    status: string;
    health: Record<string, unknown>;
    statistics: {
        total_messages_received: number;
        total_messages_sent: number;
        error_count: number;
        /** Errors in the last 24 hours — Phase 15.3 addition */
        error_count_24h: number;
        last_message_at: string | null;
        last_tested_at: string | null;
    };
    rate_limits: {
        current_usage: Record<string, unknown>;
        /** Current hourly usage as % of platform limit — Phase 15.3 addition */
        utilization_pct: number;
        platform_limits: {
            requests_per_minute: number;
            requests_per_hour: number;
        };
    };
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
    | 'moonshot'
    | 'deepseek'
    | 'azure_openai'
    | 'local'
    | 'custom';

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
    /** Task priority: 'low' | 'normal' | 'high' | 'urgent' | 'critical' | 'sovereign' */
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

// ─── Subtask & Critic types ───────────────────────────────────────────────────
// Shared between TasksPage, monitoring views, and any future consumers.

export interface Subtask {
    id: string;
    agentium_id?: string;
    title: string;
    status: string;
    assigned_agents?: {
        head?: string;
        lead?: string;
        task_agents?: string[];
    };
    error_info?: {
        error_count: number;
        retry_count: number;
        max_retries: number;
        last_error?: string;
    } | null;
    progress?: number;
    created_at?: string;
}

export interface CritiqueReview {
    id: string;
    task_id: string;
    subtask_id?: string;
    critic_type: string;
    critic_agentium_id: string;
    verdict: 'pass' | 'reject' | 'escalate';
    rejection_reason: string | null;
    suggestions: string | null;
    retry_count: number;
    max_retries: number;
    review_duration_ms: number;
    model_used: string | null;
    reviewed_at: string;
    can_retry?: boolean;
}

export interface CriticAgentStats {
    agentium_id: string;
    critic_specialty: 'code' | 'output' | 'plan';
    reviews_completed: number;
    vetoes_issued: number;
    escalations_issued: number;
    passes_issued: number;
    approval_rate: number;
    veto_rate: number;
    avg_review_time_ms: number;
    status: string;
    preferred_review_model: string | null;
}

export interface CriticStatsResponse {
    total_critics: number;
    total_reviews: number;
    total_vetoes: number;
    total_escalations: number;
    overall_approval_rate: number;
    by_type: Record<string, {
        count: number;
        reviews: number;
        vetoes: number;
        escalations: number;
        approval_rate: number;
    }>;
    critics?: CriticAgentStats[];
}

// ─── Constitution types ────────────────────────────────────────────────────────

export interface ConstitutionArticle {
    title: string;
    content: string;
    amended_at?: string;
}

export interface ConstitutionChangelogEntry {
    change: string;
    timestamp: string;
    previous_version?: string;
}

export interface Constitution {
    id: string;
    version: string;
    version_number: number;
    preamble: string;
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
export type {
    DashboardStats,
    AgentSummary,
    TaskSummary,
    DashboardSummaryResponse,
} from './dashboard';