import { TIER_PREFIXES } from '../constants/agents';

/** Extract the tier prefix (first character) from an agentium_id. */
export function getAgentTierPrefix(agentiumId: string | undefined | null): string {
    return agentiumId?.[0] ?? '';
}

/** Returns true for Critic agents (IDs starting with 4, 5, or 6) */
export function isCriticAgentId(agentiumId: string | undefined | null): boolean {
    const prefix = getAgentTierPrefix(agentiumId);
    return (TIER_PREFIXES.critics as readonly string[]).includes(prefix);
}

/** Returns true for Head of Council agents (ID starts with 0) */
export function isHeadAgentId(agentiumId: string | undefined | null): boolean {
    return getAgentTierPrefix(agentiumId) === TIER_PREFIXES.head;
}

/** Returns true for Council Member agents (ID starts with 1) */
export function isCouncilAgentId(agentiumId: string | undefined | null): boolean {
    return getAgentTierPrefix(agentiumId) === TIER_PREFIXES.council;
}

/** Returns true if parentId can legally be the direct parent of childId. */
export function canBeParentOf(parentId: string, childId: string): boolean {
    const parentNum = parseInt(getAgentTierPrefix(parentId) || '9', 10);
    const childNum  = parseInt(getAgentTierPrefix(childId)  || '9', 10);
    return parentNum < childNum;
}

/** Human-readable tier name for an agentium_id. */
export function getTierName(agentiumId: string | undefined | null): string {
    const map: Record<string, string> = {
        '0': 'Head of Council',
        '1': 'Council Member',
        '2': 'Lead Agent',
        '3': 'Task Agent',
        '4': 'Critic', '5': 'Critic', '6': 'Critic',
    };
    return map[getAgentTierPrefix(agentiumId)] ?? 'Unknown';
}