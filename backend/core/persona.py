"""Single source of truth for agent persona/behavior.

Persona is composed ENTIRELY from the active Constitution. No hardcoded
persona strings live here — see spec §3, §5.
"""
from typing import Any, Dict, Optional

FALLBACK_PERSONA = (
    "You are an AI agent operating within the Agentium governance system, "
    "bound by its Constitution."
)

VOICE_ADAPTATION = (
    "Respond in concise, natural spoken language suitable for text-to-speech: "
    "no markdown, no bullet lists, short sentences, conversational tone."
)

# Tier -> human label (improvement #5: tier-aware emphasis).
TIER_LABELS = {
    0: "Head of Council",
    1: "Council Member",
    2: "Lead Agent",
    3: "Task Agent",
    4: "Code Critic",
    5: "Output Critic",
    6: "Plan Critic",
}


def get_active_constitution_dict(db) -> Optional[Dict[str, Any]]:
    """Load the active Constitution row as a plain dict (live-read)."""
    from backend.models.entities.constitution import Constitution
    constitution = (
        db.query(Constitution)
        .filter_by(is_active=True)
        .order_by(Constitution.version_number.desc())
        .first()
    )
    if not constitution:
        return None
    return {
        "version": getattr(constitution, "version", "1.0"),
        "version_number": getattr(constitution, "version_number", 1),
        "agentium_id": constitution.agentium_id,
        "preamble": constitution.preamble or "",
        "articles": constitution.get_articles_dict() or {},
        "prohibited_actions": constitution.get_prohibited_actions_list() or [],
        "sovereign_preferences": constitution.get_sovereign_preferences() or {},
    }


def _article_applies_to(article_data: Dict[str, Any], tier: Optional[int]) -> bool:
    """An article may carry 'applies_to' (list of tiers); default = all tiers."""
    if tier is None:
        return True
    applies = article_data.get("applies_to")
    if not applies:
        return True
    return tier in applies or str(tier) in [str(t) for t in applies]


def build_persona_directive(
    constitution: Optional[Dict[str, Any]],
    tier: Optional[int] = None,
    channel: str = "text",
) -> str:
    """Compose the persona/behavior directive entirely from the Constitution.

    Order (spec §5): identity, persona & conduct, communication style,
    boundaries, tier emphasis, clause citations, provenance footer.
    """
    if not constitution:
        return FALLBACK_PERSONA

    parts: list[str] = []
    version = constitution.get("version", "1.0")
    agentium_id = constitution.get("agentium_id", "C00001")
    articles = constitution.get("articles", {}) or {}
    sovereign = constitution.get("sovereign_preferences", {}) or {}

    preamble = (constitution.get("preamble") or "").strip()
    if preamble:
        parts.append(f"# Identity\n{preamble}")

    persona_article = articles.get("agent_persona_and_conduct") or {}
    persona_text = (persona_article.get("content") or "").strip()
    if persona_text:
        parts.append(f"# Persona & Conduct\n{persona_text}")

    style_bits = []
    comm = sovereign.get("communication_style")
    if comm:
        style_bits.append(str(comm))
    if channel == "voice":
        style_bits.append(VOICE_ADAPTATION)
    if style_bits:
        parts.append("# Communication Style\n" + "\n".join(f"- {s}" for s in style_bits))

    prohibited = constitution.get("prohibited_actions") or []
    if prohibited:
        parts.append(
            "# Boundaries (Prohibited Actions)\n"
            + "\n".join(f"- {p}" for p in prohibited)
        )

    if tier is not None:
        label = TIER_LABELS.get(tier, "Agent")
        parts.append(f"# Your Role\nYou serve as the {label} in the Agentium hierarchy.")
        emphasised = []
        for key, data in articles.items():
            if key == "agent_persona_and_conduct":
                continue
            if _article_applies_to(data, tier):
                emphasised.append(f"- [{key}] {data.get('title', key)}")
        if emphasised:
            parts.append("# Constitutional Emphasis for Your Tier\n" + "\n".join(emphasised))

    citations = [f"- {key}: {d.get('title', key)}" for key, d in articles.items()]
    if citations:
        parts.append("# In-Effect Constitutional Clauses\n" + "\n".join(citations))

    parts.append(f"<!-- persona built from Constitution {version} ({agentium_id}) -->")
    return "\n\n".join(parts)
