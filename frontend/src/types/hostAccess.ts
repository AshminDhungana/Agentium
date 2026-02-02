// Types for host system access monitoring

export interface HostCommand {
    id: string;
    agentiumId: string;
    agentType: 'head_of_council' | 'council_member' | 'lead_agent' | 'task_agent';
    action: string;
    target: string;
    params: Record<string, any>;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
    result?: HostCommandResult;
    requestedAt: string;
    completedAt?: string;
    executionTime?: number;
}

export interface HostCommandResult {
    success: boolean;
    stdout?: string;
    stderr?: string;
    returncode?: number;
    output?: any;
    error?: string;
}

export interface HostSystemStatus {
    cpu: {
        usage: number;
        cores: number;
        load: number[];
    };
    memory: {
        total: number;
        used: number;
        free: number;
        percentage: number;
    };
    disk: {
        total: number;
        used: number;
        free: number;
        percentage: number;
        mounts: DiskMount[];
    };
    network: {
        interfaces: NetworkInterface[];
        connections: number;
    };
    containers: ContainerInfo[];
    processes: ProcessInfo[];
}

export interface DiskMount {
    device: string;
    mountpoint: string;
    fstype: string;
    total: number;
    used: number;
    available: number;
}

export interface NetworkInterface {
    name: string;
    ip: string;
    mac: string;
    status: 'up' | 'down';
    rx_bytes: number;
    tx_bytes: number;
}

export interface ContainerInfo {
    id: string;
    name: string;
    image: string;
    status: 'running' | 'exited' | 'paused' | 'restarting';
    state: string;
    ports: Record<string, any>;
    created: string;
    agentiumId?: string;
    agentType?: string;
}

export interface ProcessInfo {
    pid: number;
    name: string;
    user: string;
    cpu: number;
    memory: number;
    status: string;
    command: string;
}

export interface AuditLog {
    id: string;
    timestamp: string;
    agentiumId: string;
    agentType: string;
    action: string;
    target: string;
    level: 'info' | 'warning' | 'error' | 'critical';
    details: Record<string, any>;
    approved: boolean;
    blocked: boolean;
    blockReason?: string;
}

export interface SovereignCommand {
    command: string;
    target: 'head_of_council' | 'council' | 'specific_agent';
    targetAgentId?: string;
    params: Record<string, any>;
    requireApproval: boolean;
    timeout?: number;
}