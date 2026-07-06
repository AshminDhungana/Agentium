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

/** Returns true for any critic agent (legacy 4/5/6 or ephemeral 7/8/9). */
export function isCriticAgentId(id: string | null | undefined): boolean {
  if (!id) return false;
  return ['4', '5', '6', '7', '8', '9'].includes(id[0]);
}