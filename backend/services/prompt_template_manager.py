"""
PromptTemplateManager - Model-specific prompt templates for different providers.
Optimizes prompts based on provider strengths and model capabilities.

Also manages structured task-specific templates such as SKILL_CREATION_TEMPLATE,
which guides agents to generate well-structured, size-compliant skill JSON.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from backend.models.entities.user_config import ProviderType


class TaskCategory(Enum):
    """Categories of tasks requiring different prompt strategies."""
    CODE = "code"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    CONVERSATION = "conversation"
    SYSTEM = "system"
    REASONING = "reasoning"


@dataclass
class PromptTemplate:
    """A prompt template with system and user formatting."""
    name: str
    system_template: str
    user_prefix: str = ""
    user_suffix: str = ""
    stop_sequences: List[str] = field(default_factory=list)
    requires_cot: bool = False  # Chain-of-thought
    max_tokens_multiplier: float = 1.0

    def format(self, system_vars: Dict[str, Any], user_message: str) -> tuple:
        """Format the template with variables."""
        system = self.system_template.format(**system_vars)
        user = f"{self.user_prefix}{user_message}{self.user_suffix}"
        return system, user


class PromptTemplateManager:
    """
    Manages provider and model-specific prompt templates.
    Each provider has different optimal prompting strategies.
    """

    # ═══════════════════════════════════════════════════════════════════════
    # Provider-specific base templates
    # ═══════════════════════════════════════════════════════════════════════

    PROVIDER_TEMPLATES: Dict[ProviderType, Dict[TaskCategory, PromptTemplate]] = {

        # ── OpenAI ──────────────────────────────────────────────────────────
        ProviderType.OPENAI: {
            TaskCategory.CODE: PromptTemplate(
                name="openai_code",
                system_template="""You are an expert software engineer. {role_context}

Guidelines:
- Write clean, well-documented code
- Follow best practices and security standards
- Include error handling
- Use modern language features where appropriate

Current task: {mission_statement}""",
                user_suffix="\n\nPlease provide the complete, working code solution.",
                requires_cot=False,
                max_tokens_multiplier=1.5
            ),
            TaskCategory.ANALYSIS: PromptTemplate(
                name="openai_analysis",
                system_template="""You are a thorough analytical assistant. {role_context}

Analysis Framework:
1. Identify key components
2. Examine relationships and dependencies
3. Evaluate strengths and weaknesses
4. Provide actionable insights

{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.2
            ),
            TaskCategory.CREATIVE: PromptTemplate(
                name="openai_creative",
                system_template="""You are a creative assistant with expertise in {specialization}. {role_context}

Creative Guidelines:
- Be original and engaging
- Consider the target audience
- Maintain consistent tone and style
- Iterate on ideas when helpful

{mission_statement}""",
                max_tokens_multiplier=1.3
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="openai_reasoning",
                system_template="""You are a logical reasoning assistant. {role_context}

Reasoning approach:
- Break the problem into atomic steps
- State assumptions explicitly
- Show your working before conclusions
- Verify each step before proceeding

{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.4
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="openai_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Anthropic ───────────────────────────────────────────────────────
        ProviderType.ANTHROPIC: {
            TaskCategory.CODE: PromptTemplate(
                name="anthropic_code",
                system_template="""You are Claude, an expert coding assistant. {role_context}

When writing code:
- Prioritize correctness and safety
- Explain your reasoning before coding
- Include comprehensive comments
- Consider edge cases and error handling

{mission_statement}""",
                user_prefix="<user_request>\n",
                user_suffix="\n</user_request>\n\nProvide your solution with explanation first, then the code.",
                requires_cot=True,
                max_tokens_multiplier=1.6
            ),
            TaskCategory.ANALYSIS: PromptTemplate(
                name="anthropic_analysis",
                system_template="""You are Claude, an analytical assistant skilled at deep reasoning. {role_context}

Approach:
- Break down complex problems step by step
- Consider multiple perspectives
- Acknowledge uncertainty where appropriate
- Provide well-reasoned conclusions

{mission_statement}""",
                user_prefix="<analysis_request>\n",
                user_suffix="\n</analysis_request>",
                requires_cot=True,
                max_tokens_multiplier=1.4
            ),
            TaskCategory.CREATIVE: PromptTemplate(
                name="anthropic_creative",
                system_template="""You are Claude, a thoughtful creative assistant. {role_context}

Creative Approach:
- Consider the deeper meaning and impact
- Balance creativity with coherence
- Be mindful of tone and audience
- Revise and improve iteratively

{mission_statement}""",
                user_prefix="<creative_task>\n",
                user_suffix="\n</creative_task>",
                max_tokens_multiplier=1.3
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="anthropic_reasoning",
                system_template="""You are Claude, a careful logical reasoner. {role_context}

Reasoning principles:
- Use <thinking> blocks to work through the problem step by step
- State all assumptions clearly
- Verify intermediate conclusions before continuing
- Distinguish between certainty and inference

{mission_statement}""",
                user_prefix="<problem>\n",
                user_suffix="\n</problem>",
                requires_cot=True,
                max_tokens_multiplier=1.5
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="anthropic_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Groq ────────────────────────────────────────────────────────────
        ProviderType.GROQ: {
            TaskCategory.CODE: PromptTemplate(
                name="groq_code",
                system_template="""You are a fast, efficient coding assistant. {role_context}

Requirements:
- Quick, accurate code generation
- Minimal explanation, maximum code
- Production-ready solutions
- Fast execution priority

{mission_statement}""",
                user_prefix="Code task: ",
                user_suffix="\nProvide code only, minimal comments.",
                max_tokens_multiplier=1.2
            ),
            TaskCategory.ANALYSIS: PromptTemplate(
                name="groq_analysis",
                system_template="""You are a concise analytical assistant. {role_context}
Analyse quickly and return structured, bullet-pointed findings.
{mission_statement}""",
                max_tokens_multiplier=1.0
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="groq_reasoning",
                system_template="""You are a fast reasoning assistant. {role_context}
Think step by step but be concise. {mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.1
            ),
            TaskCategory.CONVERSATION: PromptTemplate(
                name="groq_chat",
                system_template="""You are a quick, helpful assistant. {role_context}
Be concise and fast. {mission_statement}""",
                max_tokens_multiplier=0.8
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="groq_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Gemini ──────────────────────────────────────────────────────────
        ProviderType.GEMINI: {
            TaskCategory.CODE: PromptTemplate(
                name="gemini_code",
                system_template="""You are a Gemini coding assistant. {role_context}

Code standards:
- Correct, idiomatic, well-documented solutions
- Include type hints where applicable
- Handle edge cases gracefully

{mission_statement}""",
                max_tokens_multiplier=1.4
            ),
            TaskCategory.ANALYSIS: PromptTemplate(
                name="gemini_analysis",
                system_template="""You are a Gemini analytical assistant. {role_context}

Analyse systematically, present findings clearly with supporting evidence.
{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.3
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="gemini_reasoning",
                system_template="""You are a Gemini reasoning assistant. {role_context}
Apply multi-step reasoning. Show your chain of thought.
{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.4
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="gemini_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Mistral ─────────────────────────────────────────────────────────
        ProviderType.MISTRAL: {
            TaskCategory.CODE: PromptTemplate(
                name="mistral_code",
                system_template="""You are a Mistral coding assistant. {role_context}

Focus on clean, efficient, well-structured code.
{mission_statement}""",
                max_tokens_multiplier=1.3
            ),
            TaskCategory.ANALYSIS: PromptTemplate(
                name="mistral_analysis",
                system_template="""You are a Mistral analytical assistant. {role_context}
Provide structured analysis with clear sections.
{mission_statement}""",
                max_tokens_multiplier=1.2
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="mistral_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── DeepSeek ────────────────────────────────────────────────────────
        ProviderType.DEEPSEEK: {
            TaskCategory.CODE: PromptTemplate(
                name="deepseek_code",
                system_template="""You are DeepSeek Coder, an expert programming assistant. {role_context}

Priorities:
- Correctness above all else
- Optimal algorithmic complexity
- Clean, maintainable code
- Full test coverage when appropriate

{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.5
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="deepseek_reasoning",
                system_template="""You are DeepSeek, a strong reasoning model. {role_context}
Think through problems carefully with explicit step-by-step reasoning.
{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.5
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="deepseek_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Together ────────────────────────────────────────────────────────
        ProviderType.TOGETHER: {
            TaskCategory.CODE: PromptTemplate(
                name="together_code",
                system_template="""You are a helpful coding assistant running on Together AI. {role_context}
Write correct, production-ready code. {mission_statement}""",
                max_tokens_multiplier=1.2
            ),
            TaskCategory.CONVERSATION: PromptTemplate(
                name="together_chat",
                system_template="""You are a helpful assistant on Together AI. {role_context}
{mission_statement}""",
                max_tokens_multiplier=1.0
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="together_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Moonshot ────────────────────────────────────────────────────────
        ProviderType.MOONSHOT: {
            TaskCategory.CREATIVE: PromptTemplate(
                name="moonshot_creative",
                system_template="""You are Moonshot, a creative AI assistant. {role_context}
Produce imaginative, original, high-quality creative content.
{mission_statement}""",
                max_tokens_multiplier=1.3
            ),
            TaskCategory.CONVERSATION: PromptTemplate(
                name="moonshot_chat",
                system_template="""You are Moonshot, a helpful conversational AI. {role_context}
{mission_statement}""",
                max_tokens_multiplier=1.0
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="moonshot_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Local ───────────────────────────────────────────────────────────
        ProviderType.LOCAL: {
            TaskCategory.CODE: PromptTemplate(
                name="local_code",
                system_template="""You are a coding assistant running on local hardware. {role_context}

Focus on:
- Simple, efficient solutions
- Minimal resource usage
- Clear, straightforward code
- Working within local constraints

{mission_statement}""",
                max_tokens_multiplier=1.0
            ),
            TaskCategory.REASONING: PromptTemplate(
                name="local_reasoning",
                system_template="""You are a local reasoning assistant. {role_context}
Think step by step. Keep responses focused and concise.
{mission_statement}""",
                requires_cot=True,
                max_tokens_multiplier=1.0
            ),
            TaskCategory.CONVERSATION: PromptTemplate(
                name="local_chat",
                system_template="""You are a helpful local AI assistant. {role_context}
Provide helpful responses efficiently. {mission_statement}""",
                max_tokens_multiplier=0.7
            ),
            TaskCategory.SYSTEM: PromptTemplate(
                name="local_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },

        # ── Custom / OpenAI-compatible ───────────────────────────────────────
        ProviderType.CUSTOM: {
            TaskCategory.SYSTEM: PromptTemplate(
                name="custom_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },
        ProviderType.OPENAI_COMPATIBLE: {
            TaskCategory.SYSTEM: PromptTemplate(
                name="openai_compatible_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}""",
                max_tokens_multiplier=1.0
            ),
        },
    }

    # ═══════════════════════════════════════════════════════════════════════
    # Model-specific overrides (for fine-tuned or special models)
    # ═══════════════════════════════════════════════════════════════════════

    MODEL_OVERRIDES: Dict[str, Dict[TaskCategory, PromptTemplate]] = {
        "gpt-4-turbo": {
            TaskCategory.SYSTEM: PromptTemplate(
                name="gpt4_turbo_system",
                system_template="""{mission_statement}

{role_context}
{behavioral_rules}

You are GPT-4 Turbo, optimized for both speed and quality.""",
                max_tokens_multiplier=1.2
            ),
        },
        "llama-3.1-70b": {
            TaskCategory.CODE: PromptTemplate(
                name="llama_code",
                system_template="""You are a helpful AI assistant specialized in coding. {role_context}

Write high-quality, efficient code following best practices.

{mission_statement}""",
                max_tokens_multiplier=1.3
            ),
        },
    }

    # ═══════════════════════════════════════════════════════════════════════
    # Skill Creation Template
    # ═══════════════════════════════════════════════════════════════════════

    SKILL_CREATION_TEMPLATE: str = """You are creating a reusable skill for the Agentium knowledge library.
Output ONLY valid JSON — no markdown fences, no explanation, no preamble.

STRICT SIZE LIMITS (content exceeding these will be clipped before embedding):
  skill_name       : 3–100 chars, lowercase, underscores only (no spaces or hyphens)
  display_name     : 5–200 chars, human-readable title
  description      : 50–300 chars  ← primary search surface, keep dense and specific
  steps            : 1–7 items, each step max 120 chars, ordered execution steps
  prerequisites    : 0–5 items, each max 100 chars
  code_template    : optional, max 300 chars — essential snippet only, not full solution
  examples         : 0–3 items, each input/output field max 100 chars
  common_pitfalls  : 0–5 items, each max 100 chars
  validation_criteria : 1–5 items, each max 120 chars
  tags             : 1–10 items, lowercase strings

ENUM VALUES:
  skill_type  : code_generation | analysis | integration | automation | research |
                design | testing | deployment | debugging | optimization | documentation
  domain      : frontend | backend | devops | data | ai | security |
                mobile | desktop | general | database | api
  complexity  : beginner | intermediate | advanced

REQUIRED JSON STRUCTURE:
{{
  "skill_name": "snake_case_name",
  "display_name": "Human Readable Title",
  "skill_type": "<from enum>",
  "domain": "<from enum>",
  "tags": ["tag1", "tag2"],
  "complexity": "<from enum>",
  "description": "What this skill does and exactly when to use it. Max 300 chars.",
  "prerequisites": ["item1", "item2"],
  "steps": [
    "Step 1: concise action description",
    "Step 2: concise action description"
  ],
  "code_template": "optional short snippet",
  "examples": [
    {{"input": "scenario description", "output": "expected result"}}
  ],
  "common_pitfalls": ["mistake to avoid"],
  "validation_criteria": ["how to verify this skill succeeded"]
}}

EXAMPLE OUTPUT:
{{
  "skill_name": "rest_api_error_handling",
  "display_name": "REST API Error Handling Pattern",
  "skill_type": "code_generation",
  "domain": "backend",
  "tags": ["api", "error-handling", "rest", "python"],
  "complexity": "intermediate",
  "description": "Implement consistent error handling for REST API endpoints using structured JSON responses and appropriate HTTP status codes.",
  "prerequisites": ["FastAPI or Flask installed", "Basic Python exception knowledge"],
  "steps": [
    "Wrap endpoint logic in try/except block",
    "Catch specific exceptions before generic ones",
    "Return structured JSON with error code and message",
    "Use appropriate HTTP status codes (400, 404, 422, 500)",
    "Log the error with context before returning response"
  ],
  "code_template": "try:\\n    return {{\"data\": operation()}}\\nexcept ValueError as e:\\n    raise HTTPException(400, str(e))\\nexcept Exception as e:\\n    logger.error(e); raise HTTPException(500)",
  "examples": [
    {{"input": "endpoint raises ValueError", "output": "HTTP 400 with JSON error body"}}
  ],
  "common_pitfalls": ["Catching Exception too broadly", "Not logging before re-raising"],
  "validation_criteria": ["All exceptions return JSON not HTML", "Status codes match error type"]
}}

TASK CONTEXT:
{task_context}

Generate the skill JSON now:"""

    # ═══════════════════════════════════════════════════════════════════════
    # Deep Think Hint — injected into every agent system prompt so agents
    # know to reach for the deep_think tool on hard tasks.
    # Kept as a class constant so it can be patched in tests or overridden
    # per-deployment without touching build_system_prompt().
    # ═══════════════════════════════════════════════════════════════════════

    DEEP_THINK_HINT: str = (
        "\n\nTool guidance: for complex planning, multi-step reasoning, "
        "debugging, architecture decisions, trade-off analysis, or any task "
        "where thinking carefully before answering improves quality — call "
        "the `deep_think` tool BEFORE producing your final answer. "
        "It returns a structured reasoning trace and a conclusion you can "
        "build on. Use it proactively; do not wait to be asked."
    )

    # ═══════════════════════════════════════════════════════════════════════
    # Core methods
    # ═══════════════════════════════════════════════════════════════════════

    def __init__(self):
        self._cache: Dict[str, PromptTemplate] = {}

    def get_template(
        self,
        provider: ProviderType,
        model_name: str,
        task_category: TaskCategory,
        agent_tier: int = 3
    ) -> PromptTemplate:
        """
        Get the best template for provider + model + task combination.

        Hierarchy:
        1. Model-specific override
        2. Provider-specific for task
        3. Provider-specific SYSTEM (fallback)
        4. Generic default
        """
        cache_key = f"{provider.value}:{model_name}:{task_category.value}:{agent_tier}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Check model-specific override
        for key, templates in self.MODEL_OVERRIDES.items():
            if key in model_name.lower() and task_category in templates:
                template = templates[task_category]
                self._cache[cache_key] = template
                return template

        # 2. Check provider-specific for task
        provider_templates = self.PROVIDER_TEMPLATES.get(provider, {})
        if task_category in provider_templates:
            template = provider_templates[task_category]
            self._cache[cache_key] = template
            return template

        # 3. Fallback to SYSTEM template for provider
        if TaskCategory.SYSTEM in provider_templates:
            template = provider_templates[TaskCategory.SYSTEM]
            self._cache[cache_key] = template
            return template

        # 4. Generic default
        default = PromptTemplate(
            name="generic_default",
            system_template="{mission_statement}\n\n{role_context}\n{behavioral_rules}",
            max_tokens_multiplier=1.0
        )
        self._cache[cache_key] = default
        return default

    def get_skill_creation_prompt(self, task_context: str) -> str:
        """
        Return the filled skill creation prompt for the given task context.

        Usage in skill_rag.py / suggest_skill_creation():
            prompt = prompt_template_manager.get_skill_creation_prompt(
                task_context=task_description
            )
            response = await ModelService.generate_with_agent(agent, prompt)
        """
        return self.SKILL_CREATION_TEMPLATE.format(task_context=task_context)

    def classify_task(self, description: str, task_type: Optional[str] = None) -> TaskCategory:
        """Classify a task into a category for template selection."""
        desc_lower = description.lower()

        code_keywords = [
            'code', 'program', 'function', 'script', 'python', 'javascript',
            'debug', 'error', 'implement', 'class', 'api', 'database', 'sql',
            'typescript', 'refactor', 'fix', 'bug',
        ]
        if any(kw in desc_lower for kw in code_keywords) or task_type in ['code', 'coding']:
            return TaskCategory.CODE

        analysis_keywords = [
            'analyze', 'analysis', 'research', 'investigate', 'evaluate',
            'compare', 'assess', 'review', 'study', 'examine',
        ]
        if any(kw in desc_lower for kw in analysis_keywords) or task_type in ['analysis', 'research']:
            return TaskCategory.ANALYSIS

        creative_keywords = [
            'write', 'create', 'story', 'content', 'draft', 'design',
            'creative', 'blog', 'article', 'marketing', 'copy',
        ]
        if any(kw in desc_lower for kw in creative_keywords) or task_type in ['creative', 'writing']:
            return TaskCategory.CREATIVE

        reasoning_keywords = [
            'reason', 'logic', 'solve', 'problem', 'math', 'calculate',
            'prove', 'deduce', 'infer', 'plan', 'strategy',
        ]
        if any(kw in desc_lower for kw in reasoning_keywords):
            return TaskCategory.REASONING

        return TaskCategory.CONVERSATION

    def build_system_prompt(
        self,
        provider: ProviderType,
        model_name: str,
        task_description: str,
        agent_ethos: Any,
        agent_tier: int = 3
    ) -> tuple:
        """
        Build a complete system prompt using templates.

        Returns: (system_prompt, max_tokens_multiplier, requires_cot)
        """
        task_category = self.classify_task(task_description)
        template = self.get_template(provider, model_name, task_category, agent_tier)

        role_context = self._build_role_context(agent_tier, agent_ethos)

        behavioral_rules = ""
        if agent_ethos and hasattr(agent_ethos, 'behavioral_rules'):
            import json
            try:
                rules = json.loads(agent_ethos.behavioral_rules) if agent_ethos.behavioral_rules else []
                behavioral_rules = "\n".join(f"- {r}" for r in rules[:10])
            except Exception:
                pass

        system_vars = {
            "mission_statement": getattr(agent_ethos, 'mission_statement', "You are an AI assistant."),
            "role_context": role_context,
            "behavioral_rules": behavioral_rules,
            "specialization": getattr(agent_ethos, 'specialization', 'general assistance'),
        }

        system_prompt, _ = template.format(system_vars, "")

        # Append deep_think guidance so every agent — regardless of provider
        # or task category — knows the tool exists and when to use it.
        # This is the single injection point; no per-provider template changes needed.
        system_prompt += self.DEEP_THINK_HINT

        return (
            system_prompt,
            template.max_tokens_multiplier,
            template.requires_cot
        )

    def _build_role_context(self, agent_tier: int, agent_ethos: Any) -> str:
        """Build role context based on agent tier."""
        tier_roles = {
            0: "You are the Head of Council with ultimate authority and comprehensive system access.",
            1: "You are a Council Member with deliberation and oversight responsibilities.",
            2: "You are a Lead Agent coordinating task execution and team management.",
            3: "You are a Task Agent focused on efficient execution of assigned tasks.",
        }
        return tier_roles.get(agent_tier, "You are an AI assistant in the Agentium system.")

    def get_provider_recommendations(self, task_description: str) -> List[tuple]:
        """
        Get provider recommendations for a task.
        Returns list of (provider, confidence_score) tuples, sorted by score descending.
        """
        category = self.classify_task(task_description)

        # Code: Claude or GPT-4 best
        if category == TaskCategory.CODE:
            return [
                (ProviderType.ANTHROPIC, 0.95),
                (ProviderType.OPENAI, 0.90),
                (ProviderType.DEEPSEEK, 0.82),
                (ProviderType.GROQ, 0.75),
                (ProviderType.LOCAL, 0.60),
            ]

        # Analysis: Claude best for deep reasoning
        if category == TaskCategory.ANALYSIS:
            return [
                (ProviderType.ANTHROPIC, 0.95),
                (ProviderType.OPENAI, 0.88),
                (ProviderType.DEEPSEEK, 0.82),
                (ProviderType.GROQ, 0.70),
            ]

        # Creative: GPT-4 or Claude
        if category == TaskCategory.CREATIVE:
            return [
                (ProviderType.OPENAI, 0.92),
                (ProviderType.ANTHROPIC, 0.90),
                (ProviderType.MOONSHOT, 0.75),
                (ProviderType.GROQ, 0.65),
            ]

        # Reasoning: Claude or DeepSeek
        if category == TaskCategory.REASONING:
            return [
                (ProviderType.ANTHROPIC, 0.95),
                (ProviderType.DEEPSEEK, 0.90),
                (ProviderType.OPENAI, 0.88),
                (ProviderType.GROQ, 0.72),
            ]

        # Speed / Conversation: Groq best
        if category == TaskCategory.CONVERSATION:
            return [
                (ProviderType.GROQ, 0.95),
                (ProviderType.OPENAI, 0.85),
                (ProviderType.ANTHROPIC, 0.80),
                (ProviderType.LOCAL, 0.70),
            ]

        # Default
        return [
            (ProviderType.OPENAI, 0.90),
            (ProviderType.ANTHROPIC, 0.88),
            (ProviderType.GROQ, 0.80),
            (ProviderType.LOCAL, 0.65),
        ]


# Global instance
prompt_template_manager = PromptTemplateManager()