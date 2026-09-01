# backend/tests/integration/test_model_allocation.py
import pytest
from backend.services.model_allocation import ModelAllocationService, init_model_allocator
from backend.services.token_optimizer import token_optimizer, init_token_optimizer
from backend.services.api_manager import init_api_manager
from backend.models.entities.agents import Agent, AgentStatus, AgentType
from backend.models.entities.task import Task, TaskType, TaskPriority, TaskStatus
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus

@pytest.mark.asyncio
async def test_model_allocator_tier_matrix(seeded_db):
    """Verify allocator picks correct capability per tier/task_type."""
    # Initialize services
    init_api_manager(seeded_db)
    init_model_allocator(seeded_db)
    init_token_optimizer(seeded_db)
    
    from backend.services.model_allocation import model_allocator
    from backend.services import api_manager as api_manager_module
    
    # Create model configs for different capabilities
    code_model = UserModelConfig(
        user_id=None,  # System config
        provider=ProviderType.OPENAI,
        config_name="test_code_model",
        default_model="gpt-4o",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
        is_default=False,
    )
    seeded_db.add(code_model)
    
    analysis_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.ANTHROPIC,
        config_name="test_analysis_model",
        default_model="claude-3-sonnet",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
        is_default=False,
    )
    seeded_db.add(analysis_model)
    
    simple_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.LOCAL,
        config_name="test_simple_model",
        default_model="kimi-2.5-7b",
        api_key_encrypted=None,
        status=ConnectionStatus.ACTIVE,
        is_default=False,
    )
    seeded_db.add(simple_model)
    seeded_db.commit()
    
    # Add to API manager
    api_manager_module.api_manager._load_configs()
    
    # Create agents of each tier
    agents = {}
    for tier, agentium_id in [(0, "00001"), (1, "10001"), (2, "20001"), (3, "30001"), (7, "70001")]:
        agent = Agent(
            agentium_id=agentium_id,
            name=f"Agent {agentium_id}",
            agent_type=AgentType.COUNCIL if tier <= 1 else AgentType.LEAD if tier == 2 else AgentType.TASK,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=tier <= 1,
        )
        seeded_db.add(agent)
        agents[tier] = agent
    seeded_db.commit()
    
    # Test CODE task - all tiers should get CODE capability
    code_task = Task(
        agentium_id="TASK-CODE-1",
        task_type=TaskType.CODE_GENERATION,
        description="Write a function",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(code_task)
    seeded_db.commit()
    
    for tier, agent in agents.items():
        config_id = model_allocator.allocate_model(agent, code_task)
        model = api_manager_module.api_manager.models.get(config_id)
        assert model.capability.value == "code", f"Tier {tier} agent should get CODE capability for code task"
    
    # Test ANALYSIS task - tier 0,1 should get HIGH_QUALITY (CODE), tier 2+ should get ANALYSIS
    analysis_task = Task(
        agentium_id="TASK-ANALYSIS-1",
        task_type=TaskType.SYSTEM_ANALYSIS,
        description="Analyze system",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(analysis_task)
    seeded_db.commit()
    
    for tier, agent in agents.items():
        config_id = model_allocator.allocate_model(agent, analysis_task)
        model = api_manager_module.api_manager.models.get(config_id)
        if tier in [0, 1]:  # Head, Council
            assert model.capability.value == "code", f"Tier {tier} should get CODE for analysis"
        elif tier == 2:  # Lead
            assert model.capability.value == "analysis", f"Tier {tier} should get ANALYSIS"
        elif tier in [3, 7]:  # Task, Critic
            assert model.capability.value in ["analysis", "simple"], f"Tier {tier} should get ANALYSIS or SIMPLE"
    
    # Test SIMPLE task - tier 0,1 get HIGH_QUALITY, tier 2 get BALANCED, tier 3+ get BUDGET/LOCAL
    simple_task = Task(
        agentium_id="TASK-SIMPLE-1",
        task_type=TaskType.SIMPLE_QUERY,
        description="Simple question",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(simple_task)
    seeded_db.commit()
    
    for tier, agent in agents.items():
        config_id = model_allocator.allocate_model(agent, simple_task)
        model = api_manager_module.api_manager.models.get(config_id)
        if tier == 0:  # Head
            assert model.capability.value == "code"
        elif tier == 1:  # Council
            assert model.capability.value in ["code", "analysis"]
        elif tier == 2:  # Lead
            assert model.capability.value in ["analysis", "creative", "simple"]
        elif tier in [3, 7]:  # Task, Critic
            assert model.capability.value in ["simple", "code"]  # Task gets simple, Critic gets analysis for simple


@pytest.mark.asyncio
async def test_model_allocator_idle_mode_uses_local(seeded_db):
    """Idle mode should always use local model."""
    init_api_manager(seeded_db)
    init_model_allocator(seeded_db)
    init_token_optimizer(seeded_db)
    
    from backend.services.model_allocation import model_allocator
    from backend.services.token_optimizer import token_optimizer
    from backend.services import api_manager as api_manager_module
    
    # Create local model config
    local_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.LOCAL,
        config_name="local_kimi",
        default_model="kimi-2.5-7b",
        api_key_encrypted=None,
        status=ConnectionStatus.ACTIVE,
        is_default=False,
    )
    seeded_db.add(local_model)
    seeded_db.commit()
    api_manager_module.api_manager._load_configs()
    
    agent = Agent(
        agentium_id="30001",
        name="Task Agent",
        agent_type=AgentType.TASK,
        status=AgentStatus.ACTIVE,
        is_active=True,
    )
    seeded_db.add(agent)
    seeded_db.commit()
    
    task = Task(
        agentium_id="TASK-1",
        task_type=TaskType.CODE_GENERATION,
        description="Code task",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(task)
    seeded_db.commit()
    
    # Activate idle mode
    token_optimizer.idle_mode_active = True
    
    config_id = model_allocator.allocate_model(agent, task)
    model = api_manager_module.api_manager.models.get(config_id)
    
    assert model.provider == "LOCAL" or "local" in model.provider.lower()
    
    # Reset
    token_optimizer.idle_mode_active = False


@pytest.mark.asyncio
async def test_model_allocator_single_api_mode(seeded_db):
    """Single API mode should use the only available API for all tasks."""
    init_api_manager(seeded_db)
    init_model_allocator(seeded_db)
    init_token_optimizer(seeded_db)
    
    from backend.services.model_allocation import model_allocator
    from backend.services import api_manager as api_manager_module
    
    # Create only ONE API model
    only_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.OPENAI,
        config_name="only_openai",
        default_model="gpt-4o",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
        is_default=False,
    )
    seeded_db.add(only_model)
    seeded_db.commit()
    api_manager_module.api_manager._load_configs()
    
    agent = Agent(
        agentium_id="30001",
        name="Task Agent",
        agent_type=AgentType.TASK,
        status=AgentStatus.ACTIVE,
        is_active=True,
    )
    seeded_db.add(agent)
    seeded_db.commit()
    
    task = Task(
        agentium_id="TASK-1",
        task_type=TaskType.SIMPLE_QUERY,
        description="Simple task",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(task)
    seeded_db.commit()
    
    # Should use the only available model
    config_id = model_allocator.allocate_model(agent, task)
    model = api_manager_module.api_manager.models.get(config_id)
    
    assert model.model_name == "gpt-4o"
    assert api_manager_module.api_manager.single_api_mode() is True


@pytest.mark.asyncio
async def test_model_allocator_priority_boost(seeded_db):
    """HIGH/CRITICAL priority should boost capability."""
    init_api_manager(seeded_db)
    init_model_allocator(seeded_db)
    init_token_optimizer(seeded_db)
    
    from backend.services.model_allocation import model_allocator
    from backend.services import api_manager as api_manager_module
    
    # Create models for different capabilities
    simple_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.LOCAL,
        config_name="local_simple",
        default_model="kimi-2.5-7b",
        api_key_encrypted=None,
        status=ConnectionStatus.ACTIVE,
    )
    analysis_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.ANTHROPIC,
        config_name="analysis_claude",
        default_model="claude-3-sonnet",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
    )
    code_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.OPENAI,
        config_name="code_gpt4o",
        default_model="gpt-4o",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
    )
    seeded_db.add_all([simple_model, analysis_model, code_model])
    seeded_db.commit()
    api_manager_module.api_manager._load_configs()
    
    agent = Agent(
        agentium_id="30001",
        name="Task Agent",
        agent_type=AgentType.TASK,
        status=AgentStatus.ACTIVE,
        is_active=True,
    )
    seeded_db.add(agent)
    seeded_db.commit()
    
    # NORMAL priority SIMPLE task -> should get SIMPLE (local)
    normal_task = Task(
        agentium_id="TASK-NORMAL",
        task_type=TaskType.SIMPLE_QUERY,
        description="Normal priority",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(normal_task)
    seeded_db.commit()
    
    config_id = model_allocator.allocate_model(agent, normal_task)
    model = api_manager_module.api_manager.models.get(config_id)
    # Task agent, SIMPLE task, NORMAL priority -> SIMPLE capability
    assert model.capability.value == "simple"
    
    # HIGH priority SIMPLE task -> should get ANALYSIS (boosted)
    high_task = Task(
        agentium_id="TASK-HIGH",
        task_type=TaskType.SIMPLE_QUERY,
        description="High priority",
        priority=TaskPriority.HIGH,
    )
    seeded_db.add(high_task)
    seeded_db.commit()
    
    config_id = model_allocator.allocate_model(agent, high_task)
    model = api_manager_module.api_manager.models.get(config_id)
    # SIMPLE -> ANALYSIS boost
    assert model.capability.value == "analysis"
    
    # CRITICAL priority SIMPLE task -> should get CODE (boosted twice)
    critical_task = Task(
        agentium_id="TASK-CRITICAL",
        task_type=TaskType.SIMPLE_QUERY,
        description="Critical priority",
        priority=TaskPriority.CRITICAL,
    )
    seeded_db.add(critical_task)
    seeded_db.commit()
    
    config_id = model_allocator.allocate_model(agent, critical_task)
    model = api_manager_module.api_manager.models.get(config_id)
    # SIMPLE -> ANALYSIS -> CODE boost
    assert model.capability.value == "code"


@pytest.mark.asyncio
async def test_token_optimizer_trims_context(seeded_db):
    """Verify context trimming respects model's context_window."""
    init_api_manager(seeded_db)
    init_token_optimizer(seeded_db)
    init_model_allocator(seeded_db)
    
    from backend.services.token_optimizer import token_optimizer
    from backend.services import api_manager as api_manager_module
    from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus
    
    # Create model config with small context_window (4096)
    small_context_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.OPENAI,
        config_name="small_context_gpt",
        default_model="gpt-3.5-turbo",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
    )
    seeded_db.add(small_context_model)
    seeded_db.commit()
    
    # Manually set context_window on the loaded ModelConfig
    api_manager_module.api_manager._load_configs()
    model_config = api_manager_module.api_manager.models.get(small_context_model.id)
    if model_config:
        model_config.context_window = 4096  # Small context window for testing
    
    # Build system_prompt + many messages exceeding limit
    system_prompt = "You are a helpful assistant. " * 20  # ~400 tokens
    messages = [
        {"role": "user", "content": f"Message {i}. " * 50} for i in range(20)
    ]  # ~20 * 250 = 5000 tokens total
    
    # Call trim_context_for_agent()
    trimmed = token_optimizer.trim_context_for_agent(
        messages=messages,
        system_prompt=system_prompt,
        model_config_id=small_context_model.id,
    )
    
    # Assert result fits within (context_window * 0.85) - system_tokens
    # context_window=4096, reserve=15%, available=3481, system~400, messages budget~3081
    from backend.services.chat_context import estimate_tokens
    total_tokens = estimate_tokens(trimmed, system_prompt)
    assert total_tokens <= 3481, f"Trimmed context ({total_tokens}) exceeds budget (3481)"
    
    # Assert most recent messages preserved
    assert len(trimmed) > 0
    assert trimmed[-1]["content"] == messages[-1]["content"]  # Last message preserved


@pytest.mark.asyncio
async def test_budget_enforcement_fallback(seeded_db):
    """Verify Task agents fall back to local model when over budget."""
    init_api_manager(seeded_db)
    init_model_allocator(seeded_db)
    init_token_optimizer(seeded_db)
    
    from backend.services.model_allocation import model_allocator
    from backend.services.token_optimizer import idle_budget
    from backend.services import api_manager as api_manager_module
    from backend.models.entities.agents import Agent, AgentStatus, AgentType
    from backend.models.entities.task import Task, TaskType, TaskPriority
    from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus, ModelUsageLog
    from datetime import datetime
    
    # Create local model
    local_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.LOCAL,
        config_name="local_fallback",
        default_model="kimi-2.5-7b",
        api_key_encrypted=None,
        status=ConnectionStatus.ACTIVE,
    )
    seeded_db.add(local_model)
    
    # Create expensive API model
    expensive_model = UserModelConfig(
        user_id=None,
        provider=ProviderType.OPENAI,
        config_name="expensive_gpt4o",
        default_model="gpt-4o",
        api_key_encrypted="encrypted_key",
        status=ConnectionStatus.ACTIVE,
    )
    seeded_db.add(expensive_model)
    seeded_db.commit()
    
    api_manager_module.api_manager._load_configs()
    
    # Set daily_cost_limit very low ($0.01)
    idle_budget.update_limits(daily_token_limit=100000, daily_cost_limit=0.01)
    
    # Create Task agent (tier 3)
    agent = Agent(
        agentium_id="30001",
        name="Task Agent",
        agent_type=AgentType.TASK,
        status=AgentStatus.ACTIVE,
        is_active=True,
    )
    seeded_db.add(agent)
    seeded_db.commit()
    
    # Create analysis task
    task = Task(
        agentium_id="TASK-1",
        task_type=TaskType.SYSTEM_ANALYSIS,
        description="Analysis task",
        priority=TaskPriority.NORMAL,
    )
    seeded_db.add(task)
    seeded_db.commit()
    
    # Mock ModelUsageLog to show near-limit usage ($0.009 used, $0.01 limit)
    usage_log = ModelUsageLog(
        agentium_id="30001",
        config_id=expensive_model.id,
        provider=ProviderType.OPENAI,
        model_used="gpt-4o",
        total_tokens=1000,
        cost_usd=0.009,  # Near the $0.01 limit
        success=True,
        created_at=datetime.utcnow(),
    )
    seeded_db.add(usage_log)
    seeded_db.commit()
    
    # Assert allocation returns local model config (fallback)
    config_id = model_allocator.allocate_model(agent, task)
    model = api_manager_module.api_manager.models.get(config_id)
    
    assert model.provider == "LOCAL" or "local" in model.provider.lower()
    
    # Reset budget
    idle_budget.update_limits(daily_token_limit=100000, daily_cost_limit=5.0)