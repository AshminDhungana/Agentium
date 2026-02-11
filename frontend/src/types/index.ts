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

// Provider Types
export type ProviderType =
    | 'openai'
    | 'anthropic'
    | 'gemini'
    | 'groq'
    | 'mistral'
    | 'together'
    | 'cohere'
    | 'fireworks'
    | 'moonshot'  // Kimi 2.5
    | 'deepseek'
    | 'azure_openai'
    | 'local'      // Ollama, LM Studio
    | 'custom';    // Any OpenAI-compatible

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

export interface Agent {
    id: string;
    agentium_id: string;
    agent_type: 'head_of_council' | 'council_member' | 'lead_agent' | 'task_agent';
    name: string;
    status: 'initializing' | 'active' | 'deliberating' | 'working' | 'suspended' | 'terminated';
    model_config?: {
        config_id: string;
        config_name: string;
        provider: string;
        model: string;
    };
    parent?: string;
    subordinates: string[];
    stats: {
        tasks_completed: number;
        tasks_failed: number;
    };
    current_task?: string;
    constitution_version: string;
    is_terminated: boolean;
}

export interface Task {
    id: string;
    agentium_id?: string;          // optional - not always returned by API
    title: string;
    description: string;
    status: string;
    priority: string;
    task_type: string;             // added - "execution" | "research" | etc.
    progress: number;
    created_by?: string;           // optional - not always returned
    assigned_agents: {
        head?: string | null;
        lead?: string | null;
        task_agents: string[];     // always an array, never null
    };
    created_at: string | null;     // ISO string or null
    updated_at?: string | null;    // added
}

export interface Constitution {
    id: string;
    version: string;
    preamble: string;
    articles: Record<string, string>;
    prohibited_actions: string[];
    sovereign_preferences: Record<string, any>;
    effective_date: string;
}

export interface AgentHealthReport {
    id: string;
    monitor: string;
    subject: string;
    status: 'healthy' | 'degraded' | 'non_responsive' | 'violation_detected' | 'termination_recommended';
    health_score: number;
    metrics: {
        success_rate: number;
        avg_duration: number;
        violations: number;
        response_time: number;
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