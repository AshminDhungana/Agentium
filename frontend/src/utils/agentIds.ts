/**
 * frontend/src/utils/agentIds.ts
 *
 * Utilities for working with Agentium ID prefixes.
 *
 * Tier prefixes
 * -------------
 *   0xxxx  Head of Council
 *   1xxxx  Council Members
 *   2xxxx  Lead Agents
 *   3xxxx  Task Agents
 *   4xxxx  (legacy) Code Critics (permanent singletons — deprecated)
 *   5xxxx  (legacy) Output Critics (permanent singletons — deprecated)
 *   6xxxx  (legacy) Plan Critics (permanent singletons — deprecated)
 *   7xxxx  Code Critics (ephemeral, per-task)
 *   8xxxx  Output Critics (ephemeral, per-task)
 *   9xxxx  Plan Critics (ephemeral, per-task)
 */

/** Agent types that are critics (independent judiciary).
 *  Ephemeral per-task critics only — see backend AgentType. The legacy 4/5/6
 *  prefixes are now reused for Task Agents, so they are NOT critics. */
export const CRITIC_AGENT_TYPES = ['code_critic', 'output_critic', 'plan_critic'] as const;

/** Returns true for a critic agent type. Prefer this over prefix checks. */
export function isCriticType(agentType: string | null | undefined): boolean {
  if (!agentType) return false;
  return (CRITIC_AGENT_TYPES as readonly string[]).includes(agentType);
}

/**
 * Returns true for a critic agent id prefix.
 *
 * Only 7/8/9 are reserved for critics (code/output/plan). Task Agents may be
 * assigned prefixes 3–6 by the backend (Agent._generate_agentium_id), so 4/5/6
 * are NOT critics. Prefer `isCriticType(agent.agent_type)` when available.
 */
export function isCriticAgentId(id: string | null | undefined): boolean {
  if (!id) return false;
  return ['7', '8', '9'].includes(id[0]);
}