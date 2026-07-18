---
name: tool_creator
description: >-
  Head or Council agents use the tool_creator tool to define and register a new
  runtime tool for themselves. Full reference in backend/.agentium/skills/tool_creator/SKILL.md.
skill_type: automation
domain: backend
complexity: advanced
tags: [tool-creation, agent-tools, governance]
creator_tier: head
---

# Tool Creator

Let a Head (0xxxx) or Council (1xxxx) agent create a new callable tool at runtime.

## Steps
1. Call tool_creator(action="create", tool_name=..., description=..., parameters=[...], code_template=..., rationale=...).
2. code_template is Python validated by ToolFactory: no eval/exec/os.system/subprocess; only whitelisted imports.
3. Head-created tools auto-activate and are invokable the same session. Council-created tools enter a democratic Council vote, then activate on approval.
4. authorized_tiers is clamped to 0xxxx/1xxxx — you cannot grant created tools to Task (3xxxx-6xxxx) or Critic (7xxxx-9xxxx) tiers.

## Validation
- tool_creator appears in list_tools for 0xxxx and 1xxxx only.
- A Head-created tool shows status "activated" and is callable immediately.
- A Council-created tool returns status "pending_vote" until the Council approves.
