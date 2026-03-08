// ─── Agent Type Constants ─────────────────────────────────────────────────────

export const VALID_AGENT_TYPES = [
    'head_of_council',
    'council_member',
    'lead_agent',
    'task_agent',
] as const;

export type ValidAgentType = typeof VALID_AGENT_TYPES[number];

export const AGENT_TYPE_LABELS: Record<string, string> = {
    head_of_council: 'Head of Council',
    council_member:  'Council Member',
    lead_agent:      'Lead Agent',
    task_agent:      'Task Agent',
};

export const AGENT_TYPE_COLORS: Record<string, {
    light: { bg: string; text: string; dot: string };
    dark:  { bg: string; text: string; dot: string; border: string };
}> = {
    head_of_council: {
        light: { bg: 'bg-violet-50',  text: 'text-violet-700',  dot: 'bg-violet-500'  },
        dark:  { bg: 'dark:bg-violet-500/10', text: 'dark:text-violet-300', dot: 'dark:bg-violet-400', border: 'dark:border-violet-500/20' },
    },
    council_member: {
        light: { bg: 'bg-blue-50',    text: 'text-blue-700',    dot: 'bg-blue-500'    },
        dark:  { bg: 'dark:bg-blue-500/10',   text: 'dark:text-blue-300',   dot: 'dark:bg-blue-400',   border: 'dark:border-blue-500/20'   },
    },
    lead_agent: {
        light: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
        dark:  { bg: 'dark:bg-emerald-500/10',text: 'dark:text-emerald-300',dot: 'dark:bg-emerald-400',border: 'dark:border-emerald-500/20' },
    },
    task_agent: {
        light: { bg: 'bg-slate-100',  text: 'text-slate-600',   dot: 'bg-slate-400'   },
        dark:  { bg: 'dark:bg-slate-500/10',  text: 'dark:text-slate-400',  dot: 'dark:bg-slate-500',  border: 'dark:border-slate-600/30'  },
    },
};

// ─── Validation Constraints — must mirror backend Pydantic field constraints ──

export const AGENT_REASON_MIN_LENGTH = 20;
export const AGENT_REASON_MAX_LENGTH = 500;
export const AGENT_NAME_MIN_LENGTH   = 3;
export const AGENT_NAME_MAX_LENGTH   = 100;
export const AGENT_DESC_MIN_LENGTH   = 10;
export const AGENT_DESC_MAX_LENGTH   = 500;

// ─── WebSocket Event Types emitted by backend lifecycle routes ────────────────

export const AGENT_WS_EVENT_TYPES = [
    'agent_spawned',
    'agent_liquidated',
    'agent_promoted',
    'agent_status_changed',
] as const;

/** Legacy string-prefix events still sent via system messages */
export const AGENT_WS_CONTENT_PREFIXES = [
    'agent_spawned',
    'agent_terminated',
    'agent_status',
    'agent_updated',
    'agent_promoted',
    'agent_liquidated',
] as const;

export function isAgentWsEvent(type: string, content?: string | null): boolean {
    if ((AGENT_WS_EVENT_TYPES as readonly string[]).includes(type)) return true;
    if (content) {
        return (AGENT_WS_CONTENT_PREFIXES as readonly string[]).some(p => content.startsWith(p));
    }
    return false;
}

// ─── Tier ID Prefixes ─────────────────────────────────────────────────────────

export const TIER_PREFIXES = {
    head:    '0',
    council: '1',
    lead:    '2',
    task:    '3',
    critics: ['4', '5', '6'],
} as const;