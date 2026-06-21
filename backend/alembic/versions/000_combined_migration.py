"""Combined Migration — All Migrations in One File

Revision ID: 000_combined_migration
Revises: (none — this is the root migration)
Create Date: 2026-05-31
"""

import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.dialects import postgresql

# ── Revision identifiers ──────────────────────────────────────────────────────
revision      = "000_combined_migration"
down_revision = None
branch_labels = None
depends_on    = None

# ── Tables the db_maintenance service should ANALYZE ─────────────────────────
ANALYZE_TABLES = [
    'agents', 'tasks', 'subtasks', 'individual_votes', 'voting_records',
    'amendment_votings', 'task_deliberations', 'monitoring_alerts',
    'constitutions', 'skills', 'skill_submissions', 'experiments',
    'experiment_runs', 'experiment_results',
]

# ── Enum objects for 006_wait_poll (create_type=False — DO $$ blocks handle creation) ──
wait_strategy_enum = postgresql.ENUM(
    "http_poll", "redis_key", "timeout", "webhook", "manual",
    name="waitstrategy",
    create_type=False,
)
wait_condition_status_enum = postgresql.ENUM(
    "pending", "active", "resolved", "expired", "cancelled",
    name="waitconditionstatus",
    create_type=False,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _col_names(inspector: Inspector, table: str):
    return {col['name'] for col in inspector.get_columns(table)}

def _index_exists(inspector: Inspector, table: str, index_name: str) -> bool:
    return any(idx['name'] == index_name for idx in inspector.get_indexes(table))

def _constraint_exists(inspector: Inspector, table: str, name: str) -> bool:
    try:
        return any(uc.get('name') == name for uc in inspector.get_unique_constraints(table))
    except Exception:
        return False

def _fk_names(inspector: Inspector, table: str):
    return {fk.get('name') for fk in inspector.get_foreign_keys(table)}


# =============================================================================
# UPGRADE
# =============================================================================

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🚀 Starting 000_combined_migration ...")

    # =========================================================================
    # [001] ENUM TYPES — created upfront so every table can reference them
    # =========================================================================

    # taskstatus — both lower and UPPER variants (app sends UPPER)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                CREATE TYPE taskstatus AS ENUM (
                    'pending', 'deliberating', 'approved', 'rejected', 'delegating',
                    'assigned', 'in_progress', 'review', 'completed', 'failed',
                    'cancelled', 'escalated',
                    'idle_pending', 'idle_running', 'idle_paused', 'idle_completed',
                    'PENDING', 'DELIBERATING', 'APPROVED', 'REJECTED', 'DELEGATING',
                    'ASSIGNED', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'FAILED',
                    'CANCELLED', 'ESCALATED',
                    'IDLE_PENDING', 'IDLE_RUNNING', 'IDLE_PAUSED', 'IDLE_COMPLETED'
                );
            END IF;
        END $$;
    """)

    # tasktype — both lower and UPPER variants (idle governance sends UPPER)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tasktype') THEN
                CREATE TYPE tasktype AS ENUM (
                    'constitutional', 'system', 'one_time', 'recurring',
                    'execution', 'research', 'automation', 'analysis', 'communication',
                    'constitution_read',       'CONSTITUTION_READ',
                    'constitution_refine',     'CONSTITUTION_REFINE',
                    'predictive_planning',     'PREDICTIVE_PLANNING',
                    'preference_optimization', 'PREFERENCE_OPTIMIZATION',
                    'vector_maintenance',      'VECTOR_MAINTENANCE',
                    'storage_dedupe',          'STORAGE_DEDUPE',
                    'audit_archival',          'AUDIT_ARCHIVAL',
                    'agent_health_scan',       'AGENT_HEALTH_SCAN',
                    'ethos_optimization',      'ETHOS_OPTIMIZATION',
                    'cache_optimization',      'CACHE_OPTIMIZATION',
                    'idle_completed',          'IDLE_COMPLETED',
                    'idle_paused',             'IDLE_PAUSED'
                );
            END IF;
        END $$;
    """)

    # taskpriority — both lower and UPPER variants (app sends UPPER)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskpriority') THEN
                CREATE TYPE taskpriority AS ENUM (
                    'sovereign', 'critical', 'high', 'normal', 'low', 'idle',
                    'SOVEREIGN', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW', 'IDLE'
                );
            END IF;
        END $$;
    """)

    # =========================================================================
    # [001-1] USERS
    # =========================================================================
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('username', sa.String(50), unique=True, nullable=False),
            sa.Column('email', sa.String(100), unique=True, nullable=False),
            sa.Column('hashed_password', sa.String(255), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('is_admin', sa.Boolean(), server_default='false'),
            sa.Column('is_pending', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-2] USER MODEL CONFIGS
    # =========================================================================
    if 'user_model_configs' not in existing_tables:
        op.create_table(
            'user_model_configs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('user_id', sa.String(36), nullable=True),
            sa.Column('config_name', sa.String(100), nullable=False),
            sa.Column('provider', sa.String(30), nullable=False),
            sa.Column('provider_name', sa.String(50), nullable=True),
            sa.Column('default_model', sa.String(100), nullable=False),
            sa.Column('available_models', sa.JSON(), nullable=True),
            sa.Column('model_family', sa.String(50), nullable=True),
            sa.Column('api_key_encrypted', sa.Text(), nullable=True),
            sa.Column('api_key_masked', sa.String(10), nullable=True),
            sa.Column('api_base_url', sa.String(500), nullable=True),
            sa.Column('azure_endpoint', sa.String(500), nullable=True),
            sa.Column('azure_deployment', sa.String(100), nullable=True),
            sa.Column('local_server_url', sa.String(500), nullable=True),
            sa.Column('max_tokens', sa.Integer(), server_default='4000'),
            sa.Column('temperature', sa.Float(), server_default='0.7'),
            sa.Column('top_p', sa.Float(), server_default='1.0'),
            sa.Column('timeout_seconds', sa.Integer(), server_default='60'),
            sa.Column('rate_limit', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(20), server_default='TESTING'),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('last_tested_at', sa.DateTime(), nullable=True),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('is_default', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('total_requests', sa.Integer(), server_default='0'),
            sa.Column('total_tokens', sa.Integer(), server_default='0'),
            sa.Column('estimated_cost_usd', sa.Float(), server_default='0.0'),
            sa.Column('extra_params', sa.JSON(), nullable=True),
            sa.Column('priority', sa.Integer(), server_default='999', nullable=False),
            sa.Column('failure_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('last_failure_at', sa.DateTime(), nullable=True),
            sa.Column('cooldown_until', sa.DateTime(), nullable=True),
            sa.Column('monthly_budget_usd', sa.Float(), server_default='0.0', nullable=False),
            sa.Column('current_spend_usd', sa.Float(), server_default='0.0', nullable=False),
            sa.Column('last_spend_reset', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_user_model_configs_agentium_id', 'user_model_configs', ['agentium_id'],
                        unique=True, postgresql_where=sa.text("agentium_id IS NOT NULL"))

    # =========================================================================
    # [001-3] ETHOS
    # =========================================================================
    if 'ethos' not in existing_tables:
        op.create_table(
            'ethos',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('agent_type', sa.String(20), nullable=False),
            sa.Column('mission_statement', sa.Text(), nullable=False),
            sa.Column('core_values', sa.Text(), nullable=False),
            sa.Column('behavioral_rules', sa.Text(), nullable=False),
            sa.Column('restrictions', sa.Text(), nullable=False),
            sa.Column('capabilities', sa.Text(), nullable=False),
            sa.Column('current_objective', sa.Text(), nullable=True),
            sa.Column('active_plan', sa.Text(), nullable=True),
            sa.Column('constitutional_references', sa.JSON(), nullable=True),
            sa.Column('task_progress_markers', sa.JSON(), nullable=True),
            sa.Column('reasoning_artifacts', sa.JSON(), nullable=True),
            sa.Column('outcome_summary', sa.Text(), nullable=True),
            sa.Column('lessons_learned', sa.Text(), nullable=True),
            sa.Column('created_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('version', sa.Integer(), server_default='1'),
            sa.Column('agent_id', sa.String(36), nullable=False),
            sa.Column('verified_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('verified_at', sa.DateTime(), nullable=True),
            sa.Column('is_verified', sa.Boolean(), server_default='false'),
            sa.Column('last_updated_by_agent', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-4] AGENTS
    # =========================================================================
    if 'agents' not in existing_tables:
        op.create_table(
            'agents',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('agent_type', sa.String(20), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('custom_capabilities', sa.Text(), nullable=True),
            sa.Column('incarnation_number', sa.Integer(), server_default='1'),
            sa.Column('parent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('status', sa.String(20), server_default='initializing'),
            sa.Column('terminated_at', sa.DateTime(), nullable=True),
            sa.Column('termination_reason', sa.Text(), nullable=True),
            sa.Column('preferred_config_id', sa.String(36), sa.ForeignKey('user_model_configs.id'), nullable=True),
            sa.Column('system_prompt_override', sa.Text(), nullable=True),
            sa.Column('ethos_id', sa.String(36), sa.ForeignKey('ethos.id'), nullable=True),
            sa.Column('constitution_version', sa.String(10), nullable=True),
            sa.Column('created_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('spawned_at_task_count', sa.Integer(), server_default='0'),
            sa.Column('tasks_completed', sa.Integer(), server_default='0'),
            sa.Column('tasks_failed', sa.Integer(), server_default='0'),
            sa.Column('current_task_id', sa.String(36), nullable=True),
            sa.Column('is_persistent', sa.Boolean(), server_default='false'),
            sa.Column('idle_mode_enabled', sa.Boolean(), server_default='false'),
            sa.Column('last_idle_action_at', sa.DateTime(), nullable=True),
            sa.Column('idle_task_count', sa.Integer(), server_default='0'),
            sa.Column('idle_tokens_saved', sa.Integer(), server_default='0'),
            sa.Column('current_idle_task_id', sa.String(36), nullable=True),
            sa.Column('persistent_role', sa.String(50), nullable=True),
            sa.Column('last_constitution_read_at', sa.DateTime(), nullable=True),
            sa.Column('constitution_read_count', sa.Integer(), server_default='0'),
            sa.Column('ethos_last_read_at', sa.DateTime(), nullable=True),
            sa.Column('ethos_action_pending', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_agent_type_status', 'agents', ['agent_type', 'status'])
        op.create_index('idx_parent_id', 'agents', ['parent_id'])
        op.create_index('idx_agents_is_persistent', 'agents', ['is_persistent'])
        op.create_index('idx_agents_last_idle', 'agents', ['last_idle_action_at'])

    # =========================================================================
    # [001-5] AGENT SUBTYPE TABLES
    # =========================================================================
    if 'head_of_council' not in existing_tables:
        op.create_table(
            'head_of_council',
            sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
            sa.Column('emergency_override_used_at', sa.DateTime(), nullable=True),
            sa.Column('last_constitution_update', sa.DateTime(), nullable=True),
        )

    if 'council_members' not in existing_tables:
        op.create_table(
            'council_members',
            sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
            sa.Column('specialization', sa.String(50), nullable=True),
            sa.Column('votes_participated', sa.Integer(), server_default='0'),
            sa.Column('votes_abstained', sa.Integer(), server_default='0'),
        )

    if 'lead_agents' not in existing_tables:
        op.create_table(
            'lead_agents',
            sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
            sa.Column('team_size', sa.Integer(), server_default='0'),
            sa.Column('max_team_size', sa.Integer(), server_default='10'),
            sa.Column('department', sa.String(50), nullable=True),
            sa.Column('spawn_threshold', sa.Integer(), server_default='5'),
        )

    if 'task_agents' not in existing_tables:
        op.create_table(
            'task_agents',
            sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
            sa.Column('assigned_tools', sa.Text(), nullable=True),
            sa.Column('execution_timeout', sa.Integer(), server_default='300'),
            sa.Column('sandbox_enabled', sa.Boolean(), server_default='true'),
        )

    if 'critic_agents' not in existing_tables:
        op.create_table(
            'critic_agents',
            sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
            sa.Column('critic_specialty', sa.String(20), nullable=False),
            sa.Column('reviews_completed', sa.Integer(), server_default='0'),
            sa.Column('vetoes_issued', sa.Integer(), server_default='0'),
            sa.Column('escalations_issued', sa.Integer(), server_default='0'),
            sa.Column('passes_issued', sa.Integer(), server_default='0'),
            sa.Column('avg_review_time_ms', sa.Float(), server_default='0.0'),
            sa.Column('preferred_review_model', sa.String(100), nullable=True),
        )

    # =========================================================================
    # [001-6] CONSTITUTIONS
    # =========================================================================
    if 'constitutions' not in existing_tables:
        op.create_table(
            'constitutions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('version', sa.String(10), unique=True, nullable=False),
            sa.Column('version_number', sa.Integer(), unique=True, nullable=False),
            sa.Column('document_type', sa.String(20), nullable=False),
            sa.Column('preamble', sa.Text(), nullable=True),
            sa.Column('articles', sa.Text(), nullable=False),
            sa.Column('prohibited_actions', sa.Text(), nullable=False),
            sa.Column('sovereign_preferences', sa.Text(), nullable=False),
            sa.Column('changelog', sa.Text(), nullable=True),
            sa.Column('created_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('amendment_of', sa.String(36), sa.ForeignKey('constitutions.id'), nullable=True),
            sa.Column('replaces_version_id', sa.String(36), sa.ForeignKey('constitutions.id'), nullable=True),
            sa.Column('amendment_date', sa.DateTime(), nullable=True),
            sa.Column('amendment_reason', sa.Text(), nullable=True),
            sa.Column('effective_date', sa.DateTime(), nullable=False),
            sa.Column('archived_date', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_constitution_version', 'constitutions', ['version'])
        op.create_index('idx_constitution_version_number', 'constitutions', ['version_number'])
        op.create_index('idx_constitution_active', 'constitutions', ['is_active'])
        op.create_index('idx_constitution_effective', 'constitutions', ['effective_date'])

    # =========================================================================
    # [001-7] TASKS — uses correct enum types from the start; no patching needed
    # =========================================================================
    if 'tasks' not in existing_tables:
        op.create_table(
            'tasks',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', postgresql.ENUM(
                'pending', 'deliberating', 'approved', 'rejected', 'delegating',
                'assigned', 'in_progress', 'review', 'completed', 'failed',
                'cancelled', 'escalated',
                'idle_pending', 'idle_running', 'idle_paused', 'idle_completed',
                'PENDING', 'DELIBERATING', 'APPROVED', 'REJECTED', 'DELEGATING',
                'ASSIGNED', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'FAILED',
                'CANCELLED', 'ESCALATED',
                'IDLE_PENDING', 'IDLE_RUNNING', 'IDLE_PAUSED', 'IDLE_COMPLETED',
                name='taskstatus', create_type=False),
                server_default='pending', nullable=False),
            sa.Column('priority', postgresql.ENUM(
                'sovereign', 'critical', 'high', 'normal', 'low', 'idle',
                'SOVEREIGN', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW', 'IDLE',
                name='taskpriority', create_type=False),
                server_default='normal', nullable=False),
            sa.Column('task_type', postgresql.ENUM(
                'constitutional', 'system', 'one_time', 'recurring',
                'execution', 'research', 'automation', 'analysis', 'communication',
                'constitution_read',       'CONSTITUTION_READ',
                'constitution_refine',     'CONSTITUTION_REFINE',
                'predictive_planning',     'PREDICTIVE_PLANNING',
                'preference_optimization', 'PREFERENCE_OPTIMIZATION',
                'vector_maintenance',      'VECTOR_MAINTENANCE',
                'storage_dedupe',          'STORAGE_DEDUPE',
                'audit_archival',          'AUDIT_ARCHIVAL',
                'agent_health_scan',       'AGENT_HEALTH_SCAN',
                'ethos_optimization',      'ETHOS_OPTIMIZATION',
                'cache_optimization',      'CACHE_OPTIMIZATION',
                'idle_completed',          'IDLE_COMPLETED',
                'idle_paused',             'IDLE_PAUSED',
                name='tasktype', create_type=False),
                server_default='execution', nullable=False),
            sa.Column('created_by', sa.String(10), nullable=False),
            sa.Column('assigned_to_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('result_summary', sa.Text(), nullable=True),
            sa.Column('acceptance_criteria', sa.JSON(), nullable=True),
            sa.Column('veto_authority', sa.String(20), nullable=True),
            sa.Column('constitutional_basis', sa.Text(), nullable=True),
            sa.Column('hierarchical_id', sa.String(100), nullable=True),
            sa.Column('recurrence_pattern', sa.String(100), nullable=True),
            sa.Column('parent_task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=True),
            sa.Column('execution_plan_id', sa.String(36), nullable=True),
            sa.Column('is_idle_task', sa.Boolean(), server_default='false'),
            sa.Column('idle_task_category', sa.String(50), nullable=True),
            sa.Column('estimated_tokens', sa.Integer(), server_default='0'),
            sa.Column('tokens_used', sa.Integer(), server_default='0'),
            sa.Column('status_history', sa.JSON(), server_default='[]'),
            sa.Column('head_of_council_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('assigned_council_ids', sa.JSON(), server_default='[]'),
            sa.Column('lead_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('assigned_task_agent_ids', postgresql.JSONB(), server_default='[]'),
            sa.Column('requires_deliberation', sa.Boolean(), server_default='true'),
            sa.Column('deliberation_id', sa.String(36), nullable=True),
            sa.Column('approved_by_council', sa.Boolean(), server_default='false'),
            sa.Column('approved_by_head', sa.Boolean(), server_default='false'),
            sa.Column('execution_plan', sa.Text(), nullable=True),
            sa.Column('execution_context', sa.Text(), nullable=True),
            sa.Column('tools_allowed', sa.JSON(), server_default='[]'),
            sa.Column('sandbox_mode', sa.Boolean(), server_default='true'),
            sa.Column('result_data', sa.JSON(), nullable=True),
            sa.Column('result_files', sa.JSON(), nullable=True),
            sa.Column('completion_percentage', sa.Integer(), server_default='0'),
            sa.Column('due_date', sa.DateTime(), nullable=True),
            sa.Column('time_estimated', sa.Integer(), server_default='0'),
            sa.Column('time_actual', sa.Integer(), server_default='0'),
            sa.Column('error_count', sa.Integer(), server_default='0'),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('retry_count', sa.Integer(), server_default='0'),
            sa.Column('max_retries', sa.Integer(), server_default='5'),
            sa.Column('idempotency_key', sa.String(200), unique=True, nullable=True),
            sa.Column('supervisor_id', sa.String(20), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_tasks_idempotency_key', 'tasks', ['idempotency_key'], unique=True)

    # =========================================================================
    # [001-8] SUBTASKS
    # =========================================================================
    if 'subtasks' not in existing_tables:
        op.create_table(
            'subtasks',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id')),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', sa.String(20), server_default='pending'),
            sa.Column('assigned_to_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('execution_order', sa.Integer(), server_default='0'),
            sa.Column('result', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-9] TASK DELIBERATIONS
    # =========================================================================
    if 'task_deliberations' not in existing_tables:
        op.create_table(
            'task_deliberations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('participating_members', sa.JSON(), nullable=False),
            sa.Column('required_approvals', sa.Integer(), server_default='2'),
            sa.Column('min_quorum', sa.Integer(), server_default='2'),
            sa.Column('status', sa.String(20), server_default='pending'),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('time_limit_minutes', sa.Integer(), server_default='30'),
            sa.Column('votes_for', sa.Integer(), server_default='0'),
            sa.Column('votes_against', sa.Integer(), server_default='0'),
            sa.Column('votes_abstain', sa.Integer(), server_default='0'),
            sa.Column('final_decision', sa.String(20), nullable=True),
            sa.Column('head_overridden', sa.Boolean(), server_default='false'),
            sa.Column('head_override_reason', sa.Text(), nullable=True),
            sa.Column('head_override_at', sa.DateTime(), nullable=True),
            sa.Column('discussion_thread', sa.JSON(), server_default='[]'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # Add FK from tasks to deliberations (both tables now exist)
    try:
        op.create_foreign_key('tasks_deliberation_id_fkey', 'tasks', 'task_deliberations',
                              ['deliberation_id'], ['id'])
    except Exception:
        pass  # already exists on re-run

    # =========================================================================
    # [001-10] TASK EVENTS & AUDIT LOGS
    # =========================================================================
    if 'task_events' not in existing_tables:
        op.create_table(
            'task_events',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('event_type', sa.String(50), nullable=False),
            sa.Column('actor_id', sa.String(36), nullable=False),
            sa.Column('actor_type', sa.String(20), server_default='system'),
            sa.Column('data', sa.JSON(), server_default='{}'),
            sa.Column('sequence_number', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    if 'task_audit_logs' not in existing_tables:
        op.create_table(
            'task_audit_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('action', sa.String(50), nullable=False),
            sa.Column('action_details', sa.JSON(), server_default='{}'),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(200), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-11] AMENDMENT VOTING
    # =========================================================================
    if 'amendment_votings' not in existing_tables:
        op.create_table(
            'amendment_votings',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('amendment_id', sa.String(36), sa.ForeignKey('constitutions.id')),
            sa.Column('proposed_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('proposed_changes', sa.Text(), nullable=False),
            sa.Column('rationale', sa.Text(), nullable=False),
            sa.Column('status', sa.String(20), server_default='proposed'),
            sa.Column('required_votes', sa.Integer(), server_default='3'),
            sa.Column('eligible_voters', sa.JSON(), server_default='[]'),
            sa.Column('supermajority_threshold', sa.Integer(), server_default='66'),
            sa.Column('votes_for', sa.Integer(), server_default='0'),
            sa.Column('votes_against', sa.Integer(), server_default='0'),
            sa.Column('votes_abstain', sa.Integer(), server_default='0'),
            sa.Column('final_result', sa.String(20), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('discussion_thread', sa.JSON(), server_default='[]'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_amendment_status', 'amendment_votings', ['status'])
        op.create_index('idx_amendment_constitution', 'amendment_votings', ['amendment_id'])

    # =========================================================================
    # [001-12] INDIVIDUAL VOTES
    # =========================================================================
    if 'individual_votes' not in existing_tables:
        op.create_table(
            'individual_votes',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('amendment_voting_id', sa.String(36), sa.ForeignKey('amendment_votings.id'), nullable=True),
            sa.Column('task_deliberation_id', sa.String(36), sa.ForeignKey('task_deliberations.id'), nullable=True),
            sa.Column('voter_agentium_id', sa.String(10), nullable=False),
            sa.Column('vote', sa.String(10), nullable=False),
            sa.Column('voted_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('rationale', sa.Text(), nullable=True),
            sa.Column('vote_changed', sa.Boolean(), server_default='false'),
            sa.Column('original_vote', sa.String(10), nullable=True),
            sa.Column('changed_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        try:
            op.execute("ALTER TABLE individual_votes ADD CONSTRAINT check_vote_has_parent "
                       "CHECK (task_deliberation_id IS NOT NULL OR amendment_voting_id IS NOT NULL)")
        except Exception:
            pass

    # =========================================================================
    # [001-13] VOTING RECORDS
    # =========================================================================
    if 'voting_records' not in existing_tables:
        op.create_table(
            'voting_records',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('voter_agentium_id', sa.String(10), sa.ForeignKey('agents.agentium_id'), nullable=False),
            sa.Column('period_start', sa.DateTime(), nullable=False),
            sa.Column('period_end', sa.DateTime(), nullable=False),
            sa.Column('total_votes_cast', sa.Integer(), server_default='0'),
            sa.Column('votes_for', sa.Integer(), server_default='0'),
            sa.Column('votes_against', sa.Integer(), server_default='0'),
            sa.Column('votes_abstain', sa.Integer(), server_default='0'),
            sa.Column('votes_changed', sa.Integer(), server_default='0'),
            sa.Column('deliberations_participated', sa.Integer(), server_default='0'),
            sa.Column('deliberations_missed', sa.Integer(), server_default='0'),
            sa.Column('avg_participation_rate', sa.Integer(), server_default='0'),
            sa.Column('proposals_made', sa.Integer(), server_default='0'),
            sa.Column('proposals_accepted', sa.Integer(), server_default='0'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-14] AUDIT LOGS
    # =========================================================================
    if 'audit_logs' not in existing_tables:
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('level', sa.String(20), nullable=False),
            sa.Column('category', sa.String(30), nullable=False),
            sa.Column('actor_type', sa.String(20), nullable=False),
            sa.Column('actor_id', sa.String(100), nullable=False),  # widened from 10→100 (from 007)
            sa.Column('action', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('target_type', sa.String(50), nullable=True),
            sa.Column('target_id', sa.String(36), nullable=True),
            sa.Column('session_id', sa.String(100), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('before_state', sa.Text(), nullable=True),
            sa.Column('after_state', sa.Text(), nullable=True),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.Column('success', sa.String(1), server_default='Y', nullable=False),
            sa.Column('result_message', sa.Text(), nullable=True),
            sa.Column('error_code', sa.String(50), nullable=True),
            sa.Column('error_details', sa.Text(), nullable=True),
            sa.Column('parent_audit_id', sa.String(36), sa.ForeignKey('audit_logs.id'), nullable=True),
            sa.Column('correlation_id', sa.String(36), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('memory_delta_mb', sa.Integer(), nullable=True),
            sa.Column('screenshot_url', sa.String(500), nullable=True),  # from 003/007
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_audit_timestamp', 'audit_logs', ['created_at'])
        op.create_index('idx_audit_actor_action', 'audit_logs', ['actor_id', 'action'])
        op.create_index('idx_audit_level_category', 'audit_logs', ['level', 'category'])
        op.create_index('idx_audit_correlation', 'audit_logs', ['correlation_id'])

    # =========================================================================
    # [001-15] CHANNELS
    # =========================================================================
    if 'channels' not in existing_tables:
        op.create_table(
            'channels',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('channel_type', sa.String(20), nullable=False),
            sa.Column('webhook_url', sa.String(500), nullable=True),
            sa.Column('api_key_encrypted', sa.Text(), nullable=True),
            sa.Column('config_json', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-16] EXTERNAL CHANNELS & MESSAGES
    # =========================================================================
    if 'external_channels' not in existing_tables:
        op.create_table(
            'external_channels',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('channel_type', sa.String(20), nullable=False),
            sa.Column('status', sa.String(20), server_default='pending'),
            sa.Column('config', sa.JSON(), server_default='{}'),
            sa.Column('default_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('auto_create_tasks', sa.Boolean(), server_default='true'),
            sa.Column('require_approval', sa.Boolean(), server_default='false'),
            sa.Column('webhook_path', sa.String(100), unique=True, nullable=True),
            sa.Column('messages_received', sa.Integer(), server_default='0'),
            sa.Column('messages_sent', sa.Integer(), server_default='0'),
            sa.Column('last_message_at', sa.DateTime(), nullable=True),
            sa.Column('last_tested_at', sa.DateTime(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # Seed WhatsApp provider default (idempotent)
    op.execute("""
        UPDATE external_channels
        SET config = (
            jsonb_set(
                COALESCE(config::jsonb, '{}'::jsonb),
                '{provider}',
                '"cloud_api"'
            )
        )::json
        WHERE channel_type = 'whatsapp'
          AND (config IS NULL OR config->>'provider' IS NULL)
    """)

    if 'external_messages' not in existing_tables:
        op.create_table(
            'external_messages',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('channel_id', sa.String(36), sa.ForeignKey('external_channels.id'), nullable=False),
            sa.Column('sender_id', sa.String(200), nullable=False),
            sa.Column('sender_name', sa.String(100), nullable=True),
            sa.Column('sender_metadata', sa.JSON(), server_default='{}'),
            sa.Column('message_type', sa.String(20), server_default='text'),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('media_url', sa.String(500), nullable=True),
            sa.Column('raw_payload', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(20), server_default='received'),
            sa.Column('assigned_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=True),
            sa.Column('response_content', sa.Text(), nullable=True),
            sa.Column('responded_at', sa.DateTime(), nullable=True),
            sa.Column('responded_by_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('error_count', sa.Integer(), server_default='0'),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-17] SYSTEM SETTINGS
    # =========================================================================
    if 'system_settings' not in existing_tables:
        op.create_table(
            'system_settings',
            sa.Column('key', sa.String(128), primary_key=True),
            sa.Column('value', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.execute("""
            INSERT INTO system_settings (key, value, description, updated_at) VALUES
                ('daily_token_limit', '100000', 'Maximum tokens per day across all API providers', NOW()),
                ('daily_cost_limit',  '5.0',    'Maximum USD cost per day across all API providers',  NOW())
            ON CONFLICT (key) DO NOTHING
        """)

    # =========================================================================
    # [001-18] MODEL USAGE LOGS
    # =========================================================================
    if 'model_usage_logs' not in existing_tables:
        op.create_table(
            'model_usage_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('config_id', sa.String(36), sa.ForeignKey('user_model_configs.id'), nullable=False),
            sa.Column('provider', sa.String(30), nullable=False),
            sa.Column('model_used', sa.String(100), nullable=False),
            sa.Column('request_type', sa.String(50), server_default='chat'),
            sa.Column('total_tokens', sa.Integer(), server_default='0'),
            sa.Column('prompt_tokens', sa.Integer(), nullable=True),
            sa.Column('completion_tokens', sa.Integer(), nullable=True),
            sa.Column('latency_ms', sa.Integer(), nullable=True),
            sa.Column('success', sa.Boolean(), server_default='true'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('cost_usd', sa.Float(), nullable=True),
            sa.Column('request_metadata', sa.JSON(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_usage_config', 'model_usage_logs', ['config_id'])
        op.create_index('idx_usage_created', 'model_usage_logs', ['created_at'])
        op.create_index('idx_usage_provider', 'model_usage_logs', ['provider'])

    # =========================================================================
    # [001-19] CONVERSATIONS & CHAT MESSAGES
    # =========================================================================
    if 'conversations' not in existing_tables:
        op.create_table(
            'conversations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('context', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('last_message_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('is_deleted', sa.Boolean(), server_default='false'),
            sa.Column('is_archived', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_conv_user_updated', 'conversations', ['user_id', 'updated_at'])
        op.create_index('idx_conv_last_message', 'conversations', ['last_message_at'])

    if 'chat_messages' not in existing_tables:
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id'), nullable=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('role', sa.String(50), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('attachments', sa.JSON(), nullable=True),
            sa.Column('message_metadata', sa.JSON(), nullable=True),
            sa.Column('agent_id', sa.String(50), nullable=True),
            sa.Column('sender_channel', sa.String(50), nullable=True),
            sa.Column('message_type', sa.String(50), server_default='text', nullable=True),
            sa.Column('media_url', sa.Text(), nullable=True),
            sa.Column('silent_delivery', sa.Boolean(), server_default='false', nullable=True),
            sa.Column('external_message_id', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('is_deleted', sa.Boolean(), server_default='false'),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_chat_user_created', 'chat_messages', ['user_id', 'created_at'])
        op.create_index('idx_chat_conversation', 'chat_messages', ['conversation_id', 'created_at'])
        op.create_index('idx_chat_role', 'chat_messages', ['role'])

    # =========================================================================
    # [001-20] MONITORING TABLES
    # =========================================================================
    if 'agent_health_reports' not in existing_tables:
        op.create_table(
            'agent_health_reports',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('monitor_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('monitor_agentium_id', sa.String(10), nullable=False),
            sa.Column('subject_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('subject_agentium_id', sa.String(10), nullable=False),
            sa.Column('status', sa.String(30), server_default='healthy'),
            sa.Column('overall_health_score', sa.Float(), server_default='100.0'),
            sa.Column('task_success_rate', sa.Float(), nullable=True),
            sa.Column('avg_task_duration', sa.Integer(), nullable=True),
            sa.Column('constitution_violations_count', sa.Integer(), server_default='0'),
            sa.Column('last_response_time_ms', sa.Integer(), nullable=True),
            sa.Column('findings', sa.JSON(), nullable=True),
            sa.Column('recommendations', sa.Text(), nullable=True),
            sa.Column('reviewed_by_higher', sa.Boolean(), server_default='false'),
            sa.Column('higher_authority_notes', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_health_monitor', 'agent_health_reports', ['monitor_agent_id'])
        op.create_index('idx_health_subject', 'agent_health_reports', ['subject_agent_id'])

    if 'violation_reports' not in existing_tables:
        op.create_table(
            'violation_reports',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('reporter_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('reporter_agentium_id', sa.String(10), nullable=False),
            sa.Column('violator_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('violator_agentium_id', sa.String(10), nullable=False),
            sa.Column('severity', sa.String(20), nullable=False),
            sa.Column('violated_article', sa.String(50), nullable=True),
            sa.Column('violated_ethos_rule', sa.String(200), nullable=True),
            sa.Column('violation_type', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('evidence', sa.JSON(), nullable=True),
            sa.Column('context', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(20), server_default='open'),
            sa.Column('assigned_to', sa.String(10), nullable=True),
            sa.Column('resolution', sa.Text(), nullable=True),
            sa.Column('action_taken', sa.String(50), nullable=True),
            sa.Column('violator_terminated', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    if 'task_verifications' not in existing_tables:
        op.create_table(
            'task_verifications',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('subtask_id', sa.String(36), sa.ForeignKey('subtasks.id'), nullable=True),
            sa.Column('task_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('lead_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('submitted_output', sa.Text(), nullable=False),
            sa.Column('submitted_data', sa.JSON(), nullable=True),
            sa.Column('submitted_at', sa.DateTime(), nullable=False),
            sa.Column('checks_performed', sa.JSON(), nullable=True),
            sa.Column('constitution_compliant', sa.Boolean(), nullable=True),
            sa.Column('output_accurate', sa.Boolean(), nullable=True),
            sa.Column('meets_requirements', sa.Boolean(), nullable=True),
            sa.Column('verification_status', sa.String(20), server_default='pending'),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('revision_count', sa.Integer(), server_default='0'),
            sa.Column('corrections_made', sa.Text(), nullable=True),
            sa.Column('feedback_to_agent', sa.Text(), nullable=True),
            sa.Column('escalated_to_council', sa.Boolean(), server_default='false'),
            sa.Column('escalation_reason', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    if 'performance_metrics' not in existing_tables:
        op.create_table(
            'performance_metrics',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('calculated_by_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('period_start', sa.DateTime(), nullable=False),
            sa.Column('period_end', sa.DateTime(), nullable=False),
            sa.Column('tasks_assigned', sa.Integer(), server_default='0'),
            sa.Column('tasks_completed', sa.Integer(), server_default='0'),
            sa.Column('tasks_failed', sa.Integer(), server_default='0'),
            sa.Column('tasks_rejected', sa.Integer(), server_default='0'),
            sa.Column('avg_quality_score', sa.Float(), nullable=True),
            sa.Column('constitution_violations', sa.Integer(), server_default='0'),
            sa.Column('avg_response_time', sa.Float(), nullable=True),
            sa.Column('total_tokens_used', sa.Integer(), server_default='0'),
            sa.Column('trend', sa.String(20), nullable=True),
            sa.Column('recommended_action', sa.String(50), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    if 'monitoring_alerts' not in existing_tables:
        op.create_table(
            'monitoring_alerts',
            sa.Column('id', sa.String(36), primary_key=True),
            # agentium_id is nullable (from 002 fix)
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=True),
            sa.Column('alert_type', sa.String(50), nullable=False),
            sa.Column('severity', sa.String(20), nullable=False),
            sa.Column('detected_by_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('affected_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('alert_metadata', sa.JSON(), nullable=True),
            sa.Column('notified_agents', sa.JSON(), nullable=True),
            sa.Column('acknowledged_by', sa.String(10), nullable=True),
            sa.Column('resolved_by', sa.String(10), nullable=True),
            sa.Column('status', sa.String(20), server_default='active'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )

    # =========================================================================
    # [001-21] CRITIQUE REVIEWS
    # =========================================================================
    if 'critique_reviews' not in existing_tables:
        op.create_table(
            'critique_reviews',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('subtask_id', sa.String(36), sa.ForeignKey('subtasks.id'), nullable=True),
            sa.Column('critic_type', sa.String(20), nullable=False),
            sa.Column('critic_agentium_id', sa.String(10), nullable=False),
            sa.Column('verdict', sa.String(20), nullable=False),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('suggestions', sa.Text(), nullable=True),
            sa.Column('retry_count', sa.Integer(), server_default='0'),
            sa.Column('max_retries', sa.Integer(), server_default='5'),
            sa.Column('review_duration_ms', sa.Float(), server_default='0.0'),
            sa.Column('model_used', sa.String(100), nullable=True),
            sa.Column('output_hash', sa.String(64), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('criteria_results', sa.JSON(), nullable=True),
            sa.Column('criteria_evaluated', sa.Integer(), nullable=True),
            sa.Column('criteria_passed', sa.Integer(), nullable=True),
            sa.Column('learning_extracted', sa.Boolean(), nullable=False, server_default='false'),  # from 003/007
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_critique_task', 'critique_reviews', ['task_id'])
        op.create_index('idx_critique_critic', 'critique_reviews', ['critic_agentium_id'])

    # =========================================================================
    # [001-22] TOOL MANAGEMENT
    # =========================================================================
    if 'tool_staging' not in existing_tables:
        op.create_table(
            'tool_staging',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('tool_name', sa.String(100), nullable=False, unique=True),
            sa.Column('proposed_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('tool_path', sa.String(500), nullable=False),
            sa.Column('request_json', sa.Text(), nullable=False),
            sa.Column('requires_vote', sa.Boolean(), server_default='true'),
            sa.Column('voting_id', sa.String(36), nullable=True),
            sa.Column('status', sa.String(50), server_default='pending_approval'),
            sa.Column('current_version', sa.Integer(), server_default='1'),
            sa.Column('activated_at', sa.DateTime(), nullable=True),
            sa.Column('deprecated_at', sa.DateTime(), nullable=True),
            sa.Column('sunset_at', sa.DateTime(), nullable=True),
            sa.Column('deprecated_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('deprecation_reason', sa.Text(), nullable=True),
            sa.Column('replacement_tool_name', sa.String(100), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_tool_staging_name',     'tool_staging', ['tool_name'])
        op.create_index('idx_tool_staging_proposer', 'tool_staging', ['proposed_by_agentium_id'])
        op.create_index('idx_tool_staging_status',   'tool_staging', ['status'])

    if 'tool_versions' not in existing_tables:
        op.create_table(
            'tool_versions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('tool_name', sa.String(100), nullable=False),
            sa.Column('version_number', sa.Integer(), nullable=False),
            sa.Column('version_tag', sa.String(20), nullable=False),
            sa.Column('code_snapshot', sa.Text(), nullable=False),
            sa.Column('tool_path', sa.String(500), nullable=False),
            sa.Column('authored_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('change_summary', sa.Text(), nullable=True),
            sa.Column('approved_by_voting_id', sa.String(36), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='false'),
            sa.Column('is_rolled_back', sa.Boolean(), server_default='false'),
            sa.Column('rolled_back_from_version', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_tool_versions_name_number', 'tool_versions',
                        ['tool_name', 'version_number'], unique=True)

    if 'tool_usage_logs' not in existing_tables:
        op.create_table(
            'tool_usage_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('tool_name', sa.String(100), nullable=False),
            sa.Column('tool_version', sa.Integer(), server_default='1'),
            sa.Column('called_by_agentium_id', sa.String(10), nullable=False),
            sa.Column('task_id', sa.String(36), nullable=True),
            sa.Column('success', sa.Boolean(), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('latency_ms', sa.Float(), nullable=True),
            sa.Column('input_hash', sa.String(64), nullable=True),
            sa.Column('output_size_bytes', sa.Integer(), nullable=True),
            sa.Column('invoked_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_tool_usage_tool_invoked', 'tool_usage_logs', ['tool_name', 'invoked_at'])
        op.create_index('ix_tool_usage_agent_tool', 'tool_usage_logs', ['called_by_agentium_id', 'tool_name'])

    if 'tool_marketplace_listings' not in existing_tables:
        op.create_table(
            'tool_marketplace_listings',
            sa.Column('id', sa.String(36), primary_key=True),
            # BaseEntity columns included upfront (from 002 fix)
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('tool_name', sa.String(100), nullable=False),
            sa.Column('version_tag', sa.String(20), nullable=False),
            sa.Column('publisher_instance_id', sa.String(100), nullable=False),
            sa.Column('published_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('display_name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('category', sa.String(50), nullable=True),
            sa.Column('tags', sa.JSON(), server_default='[]'),
            sa.Column('code_snapshot', sa.Text(), nullable=False),
            sa.Column('code_hash', sa.String(64), nullable=False),
            sa.Column('parameters_schema', sa.JSON(), server_default='{}'),
            sa.Column('authorized_tiers', sa.JSON(), server_default='[]'),
            sa.Column('is_local', sa.Boolean(), server_default='true'),
            sa.Column('is_imported', sa.Boolean(), server_default='false'),
            sa.Column('import_source_url', sa.String(500), nullable=True),
            sa.Column('is_verified', sa.Boolean(), server_default='false'),
            sa.Column('trust_score', sa.Float(), server_default='0.0'),
            sa.Column('download_count', sa.Integer(), server_default='0'),
            sa.Column('rating_sum', sa.Float(), server_default='0.0'),
            sa.Column('rating_count', sa.Integer(), server_default='0'),
            sa.Column('published_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('yanked_at', sa.DateTime(), nullable=True),
            sa.Column('yank_reason', sa.Text(), nullable=True),
        )
        op.create_index('ix_tool_marketplace_listings_agentium_id',
                        'tool_marketplace_listings', ['agentium_id'], unique=True)

    # =========================================================================
    # [001-23] SCHEDULED TASKS
    # =========================================================================
    if 'scheduled_tasks' not in existing_tables:
        op.create_table(
            'scheduled_tasks',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('cron_expression', sa.String(100), nullable=False),
            sa.Column('task_payload', sa.Text(), nullable=False),
            sa.Column('owner_agentium_id', sa.String(10), nullable=False, server_default='00001'),
            sa.Column('executing_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('status', sa.String(20), server_default='active'),
            sa.Column('priority', sa.Integer(), server_default='1'),
            sa.Column('last_execution_at', sa.DateTime(), nullable=True),
            sa.Column('next_execution_at', sa.DateTime(), nullable=True),
            sa.Column('execution_count', sa.Integer(), server_default='0'),
            sa.Column('failure_count', sa.Integer(), server_default='0'),
            sa.Column('max_retries', sa.Integer(), server_default='3'),
            sa.Column('timezone', sa.String(50), server_default='UTC'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_scheduled_next_run', 'scheduled_tasks', ['next_execution_at'])
        op.create_index('idx_scheduled_owner',    'scheduled_tasks', ['owner_agentium_id'])
        op.create_index('idx_scheduled_status',   'scheduled_tasks', ['status'])

    if 'scheduled_task_executions' not in existing_tables:
        op.create_table(
            'scheduled_task_executions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('scheduled_task_id', sa.String(36), sa.ForeignKey('scheduled_tasks.id')),
            sa.Column('execution_agentium_id', sa.String(10), nullable=False),
            sa.Column('execution_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('started_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(20), server_default='running'),
            sa.Column('result_payload', sa.Text(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('retry_number', sa.Integer(), server_default='0'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_sched_exec_task', 'scheduled_task_executions', ['scheduled_task_id'])
        op.create_index('idx_sched_exec_time', 'scheduled_task_executions', ['started_at'])

    # =========================================================================
    # [001-24] EXECUTION CHECKPOINTS
    # =========================================================================
    if 'execution_checkpoints' not in existing_tables:
        op.create_table(
            'execution_checkpoints',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('session_id', sa.String(100), nullable=False),
            sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=False),
            sa.Column('phase', sa.String(50), nullable=False),
            sa.Column('agent_states', sa.JSON(), server_default='{}'),
            sa.Column('artifacts', sa.JSON(), server_default='[]'),
            sa.Column('task_state_snapshot', sa.JSON(), server_default='{}'),
            sa.Column('parent_checkpoint_id', sa.String(36), sa.ForeignKey('execution_checkpoints.id'), nullable=True),
            sa.Column('branch_name', sa.String(100), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_exec_ckpt_session', 'execution_checkpoints', ['session_id'])
        op.create_index('idx_exec_ckpt_task',    'execution_checkpoints', ['task_id'])

    # =========================================================================
    # [001-25] REMOTE EXECUTIONS & SANDBOXES
    # =========================================================================
    if 'remote_executions' not in existing_tables:
        op.create_table(
            'remote_executions',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('agentium_id', sa.String(10), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('execution_id', sa.String(50), nullable=False),
            sa.Column('agent_id', sa.String(20), nullable=False),
            sa.Column('task_id', sa.String(36), nullable=True),
            sa.Column('code', sa.Text(), nullable=False),
            sa.Column('language', sa.String(20), nullable=True),
            sa.Column('dependencies', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('input_data_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('expected_output_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('status', sa.String(20), nullable=True),
            sa.Column('summary', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('cpu_time_seconds', sa.Float(), nullable=True),
            sa.Column('memory_peak_mb', sa.Float(), nullable=True),
            sa.Column('execution_time_ms', sa.Integer(), nullable=True),
            sa.Column('sandbox_id', sa.String(50), nullable=True),
            sa.Column('sandbox_container_id', sa.String(100), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.agentium_id']),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('execution_id'),
        )
        op.create_index('ix_remote_executions_execution_id', 'remote_executions', ['execution_id'])
        op.create_index('ix_remote_executions_agent_id',     'remote_executions', ['agent_id'])
        op.create_index('ix_remote_executions_status',       'remote_executions', ['status'])
        op.create_index('ix_remote_executions_created_at',   'remote_executions', ['created_at'])

    if 'sandboxes' not in existing_tables:
        op.create_table(
            'sandboxes',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('agentium_id', sa.String(10), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('sandbox_id', sa.String(50), nullable=False),
            sa.Column('container_id', sa.String(100), nullable=True),
            sa.Column('status', sa.String(20), nullable=True),
            sa.Column('cpu_limit', sa.Float(), nullable=True),
            sa.Column('memory_limit_mb', sa.Integer(), nullable=True),
            sa.Column('timeout_seconds', sa.Integer(), nullable=True),
            sa.Column('network_mode', sa.String(20), nullable=True),
            sa.Column('allowed_hosts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('volume_mounts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('max_disk_mb', sa.Integer(), nullable=True),
            sa.Column('current_execution_id', sa.String(50), nullable=True),
            sa.Column('created_by_agent_id', sa.String(5), nullable=False),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('destroyed_at', sa.DateTime(), nullable=True),
            sa.Column('destroy_reason', sa.String(100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('sandbox_id'),
        )
        op.create_index('ix_sandboxes_sandbox_id', 'sandboxes', ['sandbox_id'])
        op.create_index('ix_sandboxes_agent_id',   'sandboxes', ['created_by_agent_id'])
        op.create_index('ix_sandboxes_status',     'sandboxes', ['status'])

    # =========================================================================
    # [001-26] MCP TOOLS
    # =========================================================================
    if 'mcp_tools' not in existing_tables:
        op.create_table(
            'mcp_tools',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('server_url', sa.String(512), nullable=False),
            sa.Column('tier', sa.String(32), nullable=False, server_default='restricted'),
            sa.Column('constitutional_article', sa.String(64), nullable=True),
            sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
            sa.Column('approved_by_council', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('approval_vote_id', sa.String(64), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by', sa.String(64), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_by', sa.String(64), nullable=True),
            sa.Column('revocation_reason', sa.Text(), nullable=True),
            sa.Column('capabilities', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('health_status', sa.String(32), nullable=False, server_default='unknown'),
            sa.Column('last_health_check_at', sa.DateTime(), nullable=True),
            sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('audit_log', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('proposed_by', sa.String(64), nullable=True),
            sa.Column('proposed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_mcp_tools_agentium_id', 'mcp_tools', ['agentium_id'], unique=True)
        op.create_index('ix_mcp_tools_name',        'mcp_tools', ['name'],        unique=True)
        op.create_index('ix_mcp_tools_server_url',  'mcp_tools', ['server_url'],  unique=False)
        op.create_index('ix_mcp_tools_status',      'mcp_tools', ['status'],      unique=False)
        op.create_index('ix_mcp_tools_tier',        'mcp_tools', ['tier'],        unique=False)

    # =========================================================================
    # [001-27] USER PREFERENCES
    # =========================================================================
    if 'user_preferences' not in existing_tables:
        op.create_table(
            'user_preferences',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True, index=True),
            sa.Column('category', sa.String(50), nullable=False, server_default='general', index=True),
            sa.Column('key', sa.String(255), nullable=False, index=True),
            sa.Column('value_json', sa.Text(), nullable=False),
            sa.Column('data_type', sa.String(20), nullable=False, server_default='string'),
            sa.Column('scope', sa.String(20), nullable=False, server_default='global', index=True),
            sa.Column('scope_target_id', sa.String(20), nullable=True, index=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_editable_by_agents', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('last_modified_by_agent', sa.String(10), nullable=True),
            sa.Column('last_agent_modified_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_user_pref_user_cat',       'user_preferences', ['user_id', 'category'])
        op.create_index('idx_user_pref_key_scope',      'user_preferences', ['key', 'scope', 'scope_target_id'])
        op.create_index('idx_user_pref_agent_editable', 'user_preferences', ['is_editable_by_agents', 'category'])

        # Seed system-wide defaults (user_id = NULL intentionally — visible to all users)
        op.execute("""
            INSERT INTO user_preferences
                (id, agentium_id, category, key, value_json, data_type, scope,
                 description, is_editable_by_agents, created_at, updated_at)
            VALUES
                (gen_random_uuid(), 'PREF0001', 'general',       'system.name',                '"Agentium"',                   'string',  'system', 'System name displayed in UI',                    false, NOW(), NOW()),
                (gen_random_uuid(), 'PREF0002', 'ui',            'ui.theme',                   '"dark"',                       'string',  'global', 'UI theme (dark/light/auto)',                      true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0003', 'ui',            'ui.language',                '"en"',                         'string',  'global', 'UI language code',                               true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0004', 'chat',          'chat.history_limit',         '50',                           'integer', 'global', 'Maximum messages in chat history',               true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0005', 'chat',          'chat.auto_save',             'true',                         'boolean', 'global', 'Auto-save conversations',                        true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0006', 'agents',        'agents.default_timeout',     '300',                          'integer', 'global', 'Default task timeout in seconds',                true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0007', 'agents',        'agents.max_concurrent_tasks','5',                            'integer', 'global', 'Maximum concurrent tasks per agent',             true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0008', 'tasks',         'tasks.auto_archive_days',    '30',                           'integer', 'global', 'Days after which completed tasks are archived',  true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0009', 'notifications', 'notifications.enabled',      'true',                         'boolean', 'global', 'Enable notifications',                           true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0010', 'notifications', 'notifications.channels',     '["websocket", "email"]',       'json',    'global', 'Active notification channels',                   true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0011', 'models',        'models.default_temperature', '0.7',                          'float',   'global', 'Default temperature for LLM calls',              true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0012', 'privacy',       'privacy.data_retention_days','90',                           'integer', 'global', 'Data retention period in days',                  false, NOW(), NOW()),
                (gen_random_uuid(), 'PREF0013', 'tools',         'tools.max_execution_time',   '60',                           'integer', 'global', 'Maximum tool execution time in seconds',          true,  NOW(), NOW()),
                (gen_random_uuid(), 'PREF0014', 'tools',         'tools.sandbox_enabled',      'true',                         'boolean', 'global', 'Enable sandbox for tool execution',              false, NOW(), NOW())
            ON CONFLICT (agentium_id) DO NOTHING
        """)

    if 'user_preference_history' not in existing_tables:
        op.create_table(
            'user_preference_history',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('preference_id', sa.String(36), sa.ForeignKey('user_preferences.id'), nullable=False, index=True),
            sa.Column('previous_value_json', sa.Text(), nullable=False),
            sa.Column('new_value_json', sa.Text(), nullable=False),
            sa.Column('changed_by_agentium_id', sa.String(10), nullable=True),
            sa.Column('changed_by_user_id', sa.String(36), nullable=True),
            sa.Column('change_reason', sa.Text(), nullable=True),
            sa.Column('change_category', sa.String(50), server_default='manual', nullable=False),
        )

    print("✅ [001] Base schema applied")

    # =========================================================================
    # [002] ENUM TYPES for A/B testing
    # =========================================================================
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_status') THEN
                CREATE TYPE experiment_status AS ENUM (
                    'draft', 'pending', 'running', 'completed', 'failed', 'cancelled'
                );
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'run_status') THEN
                CREATE TYPE run_status AS ENUM (
                    'pending', 'running', 'completed', 'failed'
                );
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_complexity') THEN
                CREATE TYPE task_complexity AS ENUM (
                    'simple', 'medium', 'complex'
                );
            END IF;
        END $$;
    """)

    # =========================================================================
    # [002-1] A/B TESTING TABLES
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'experiments' not in existing_tables:
        op.create_table(
            'experiments',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('task_template', sa.Text(), nullable=False),
            sa.Column('system_prompt', sa.Text()),
            sa.Column('test_iterations', sa.Integer(), server_default='1'),
            sa.Column('status', postgresql.ENUM(
                'draft', 'pending', 'running', 'completed', 'failed', 'cancelled',
                name='experiment_status', create_type=False),
                server_default='draft'),
            sa.Column('created_by', sa.String(100), nullable=False, server_default='unknown'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('completed_at', sa.DateTime()),
        )
        op.create_index('idx_experiments_status',     'experiments', ['status'])
        op.create_index('idx_experiments_created_at', 'experiments', ['created_at'])

    if 'experiment_runs' not in existing_tables:
        op.create_table(
            'experiment_runs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='CASCADE')),
            sa.Column('config_id', sa.String(36),
                      sa.ForeignKey('user_model_configs.id', ondelete='SET NULL'), nullable=True),
            sa.Column('model_name', sa.String(100)),
            sa.Column('iteration_number', sa.Integer(), server_default='1'),
            sa.Column('status', postgresql.ENUM(
                'pending', 'running', 'completed', 'failed',
                name='run_status', create_type=False),
                server_default='pending'),
            sa.Column('output_text', sa.Text()),
            sa.Column('tokens_used', sa.Integer()),
            sa.Column('latency_ms', sa.Integer()),
            sa.Column('cost_usd', sa.Float()),
            sa.Column('critic_plan_score', sa.Float()),
            sa.Column('critic_code_score', sa.Float()),
            sa.Column('critic_output_score', sa.Float()),
            sa.Column('overall_quality_score', sa.Float()),
            sa.Column('critic_feedback', postgresql.JSON()),
            sa.Column('constitutional_violations', sa.Integer(), server_default='0'),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('completed_at', sa.DateTime()),
            sa.Column('error_message', sa.Text()),
        )
        op.create_index('idx_experiment_runs_experiment_id', 'experiment_runs', ['experiment_id'])
        op.create_index('idx_experiment_runs_config_id',     'experiment_runs', ['config_id'])
        op.create_index('idx_experiment_runs_status',        'experiment_runs', ['status'])

    if 'experiment_results' not in existing_tables:
        op.create_table(
            'experiment_results',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='CASCADE')),
            sa.Column('winner_config_id', sa.String(36),
                      sa.ForeignKey('user_model_configs.id', ondelete='SET NULL'), nullable=True),
            sa.Column('winner_model_name', sa.String(100)),
            sa.Column('selection_reason', sa.Text()),
            sa.Column('model_comparisons', postgresql.JSON()),
            sa.Column('statistical_significance', sa.Float()),
            sa.Column('recommended_for_similar', sa.Boolean(), server_default='false'),
            sa.Column('confidence_score', sa.Float()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('idx_experiment_results_experiment_id', 'experiment_results', ['experiment_id'])

    if 'model_performance_cache' not in existing_tables:
        op.create_table(
            'model_performance_cache',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('task_category', sa.String(50), nullable=False),
            sa.Column('task_complexity', postgresql.ENUM(
                'simple', 'medium', 'complex',
                name='task_complexity', create_type=False)),
            sa.Column('best_config_id', sa.String(36),
                      sa.ForeignKey('user_model_configs.id', ondelete='SET NULL'), nullable=True),
            sa.Column('best_model_name', sa.String(100)),
            sa.Column('avg_latency_ms', sa.Integer()),
            sa.Column('avg_cost_usd', sa.Float()),
            sa.Column('avg_quality_score', sa.Float()),
            sa.Column('success_rate', sa.Float()),
            sa.Column('derived_from_experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='SET NULL'), nullable=True),
            sa.Column('sample_size', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('idx_performance_cache_category', 'model_performance_cache', ['task_category'])
        op.create_index('idx_performance_cache_quality',  'model_performance_cache', ['avg_quality_score'])

    # =========================================================================
    # [002-2] SKILL SYSTEM TABLES
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'skills' not in existing_tables:
        op.create_table(
            'skills',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('skill_id',     sa.String(50),  nullable=False),
            sa.Column('skill_name',   sa.String(100), nullable=False),
            sa.Column('display_name', sa.String(200), nullable=False),
            sa.Column('description',  sa.String(300), nullable=True),
            sa.Column('skill_type',  sa.String(50), nullable=False),
            sa.Column('domain',      sa.String(50), nullable=False),
            sa.Column('tags',        sa.JSON(),     nullable=False, server_default='[]'),
            sa.Column('complexity',  sa.String(20), nullable=False),
            sa.Column('chroma_id',         sa.String(100), nullable=False),
            sa.Column('chroma_collection', sa.String(50),  nullable=False, server_default='agent_skills'),
            sa.Column('embedding_model',   sa.String(100), nullable=False,
                      server_default='sentence-transformers/all-MiniLM-L6-v2'),
            sa.Column('creator_tier',    sa.String(20),  nullable=False),
            sa.Column('creator_id',      sa.String(20),  nullable=False),
            sa.Column('parent_skill_id', sa.String(50),  nullable=True),
            sa.Column('task_origin',     sa.String(50),  nullable=True),
            sa.Column('success_rate',    sa.Float(),   nullable=False, server_default='0.0'),
            sa.Column('usage_count',     sa.Integer(), nullable=False, server_default='0'),
            sa.Column('retrieval_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_retrieved',  sa.DateTime(), nullable=True),
            sa.Column('constitution_compliant', sa.Boolean(),   nullable=False, server_default='false'),
            sa.Column('verification_status',    sa.String(20),  nullable=False, server_default='pending'),
            sa.Column('verified_by',            sa.String(20),  nullable=True),
            sa.Column('verified_at',            sa.DateTime(),  nullable=True),
            sa.Column('rejection_reason',       sa.String(500), nullable=True),
        )
        op.create_index('ix_skills_skill_id',           'skills', ['skill_id'],                                   unique=True)
        op.create_index('ix_skills_verification_usage', 'skills', ['verification_status', 'usage_count'])
        op.create_index('ix_skills_creator_id',         'skills', ['creator_id'])
        op.create_index('ix_skills_domain_usage',       'skills', ['domain', 'verification_status', 'usage_count'])

    if 'skill_submissions' not in existing_tables:
        op.create_table(
            'skill_submissions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=True),
            sa.Column('submission_id', sa.String(50), nullable=False),
            sa.Column('skill_id',      sa.String(50),
                      sa.ForeignKey('skills.skill_id', ondelete='CASCADE'), nullable=False),
            sa.Column('submitted_by',  sa.String(20),   nullable=False),
            sa.Column('submitted_at',  sa.DateTime(),   nullable=True, server_default=sa.text('NOW()')),
            sa.Column('status',           sa.String(20),   nullable=False, server_default='pending'),
            sa.Column('council_vote_id',  sa.String(50),   nullable=True),
            sa.Column('reviewed_by',      sa.String(20),   nullable=True),
            sa.Column('reviewed_at',      sa.DateTime(),   nullable=True),
            sa.Column('review_notes',     sa.String(1000), nullable=True),
            sa.Column('skill_data',       sa.JSON(),       nullable=False, server_default='{}'),
        )
        op.create_index('ix_skill_submissions_submission_id', 'skill_submissions', ['submission_id'], unique=True)
        op.create_index('ix_skill_submissions_skill_id',      'skill_submissions', ['skill_id'])
        op.create_index('ix_skill_submissions_status',        'skill_submissions', ['status'])
        op.create_index('ix_skill_submissions_submitted_by',  'skill_submissions', ['submitted_by'])

    # =========================================================================
    # [002-3] DB MAINTENANCE CONFIG + ANALYZE seed
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'db_maintenance_config' not in existing_tables:
        op.create_table(
            'db_maintenance_config',
            sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column('config_key', sa.String(100), nullable=False, unique=True),
            sa.Column('config_value', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )

    analyze_value = json.dumps(ANALYZE_TABLES)
    existing_row = conn.execute(text(
        "SELECT id FROM db_maintenance_config WHERE config_key = 'analyze_tables'"
    )).fetchone()
    if existing_row:
        conn.execute(text(
            "UPDATE db_maintenance_config SET config_value = :val, updated_at = NOW() "
            "WHERE config_key = 'analyze_tables'"
        ), {"val": analyze_value})
    else:
        conn.execute(text(
            "INSERT INTO db_maintenance_config (config_key, config_value, description) "
            "VALUES ('analyze_tables', :val, "
            "'JSON array of table names the db_maintenance service should ANALYZE')"
        ), {"val": analyze_value})

    # =========================================================================
    # [002-4] PostgreSQL backup helper functions
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION create_backup_sql()
        RETURNS text AS $$
        DECLARE
            result text := '';
            rec record;
        BEGIN
            FOR rec IN
                SELECT 'CREATE TABLE IF NOT EXISTS ' || tablename || ' (' ||
                    string_agg(
                        column_name || ' ' ||
                        CASE
                            WHEN data_type = 'character varying' AND character_maximum_length IS NOT NULL
                                THEN 'varchar(' || character_maximum_length || ')'
                            WHEN data_type = 'character varying'  THEN 'varchar'
                            WHEN data_type = 'integer'            THEN 'integer'
                            WHEN data_type = 'bigint'             THEN 'bigint'
                            WHEN data_type = 'boolean'            THEN 'boolean'
                            WHEN data_type = 'timestamp without time zone' THEN 'timestamp'
                            WHEN data_type = 'timestamp with time zone'    THEN 'timestamptz'
                            WHEN data_type = 'text'               THEN 'text'
                            WHEN data_type = 'json'               THEN 'json'
                            WHEN data_type = 'jsonb'              THEN 'jsonb'
                            WHEN data_type = 'uuid'               THEN 'uuid'
                            WHEN data_type = 'numeric'            THEN 'numeric'
                            WHEN data_type = 'double precision'   THEN 'float'
                            WHEN data_type = 'real'               THEN 'real'
                            ELSE data_type
                        END ||
                        CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END,
                        ', ' ORDER BY ordinal_position
                    ) || ');' AS ddl
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name NOT LIKE 'pg_%'
                AND table_name NOT LIKE 'sql_%'
                GROUP BY tablename
            LOOP
                result := result || rec.ddl || E'\n\n';
            END LOOP;
            result := result || '-- Backup generated at: ' || NOW()::text || E'\n';
            RETURN result;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION backup_table_to_json(table_name text)
        RETURNS json AS $$
        DECLARE
            result json;
            query  text;
        BEGIN
            query := 'SELECT json_agg(row_to_json(t)) FROM ' || quote_ident(table_name) || ' t';
            EXECUTE query INTO result;
            RETURN COALESCE(result, '[]'::json);
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Drop stale 'votes' table/view if present
    op.execute("DROP TABLE IF EXISTS votes CASCADE")
    op.execute("DROP VIEW IF EXISTS votes CASCADE")

    # =========================================================================
    # [002-5] individual_votes.updated_at + uppercase enum variants
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    iv_columns = {col['name'] for col in inspector.get_columns('individual_votes')}
    if 'updated_at' not in iv_columns:
        op.add_column('individual_votes', sa.Column('updated_at', sa.DateTime(), nullable=True))
        conn.execute(text("UPDATE individual_votes SET updated_at = created_at WHERE updated_at IS NULL"))
        conn.execute(text("""
            ALTER TABLE individual_votes
                ALTER COLUMN updated_at SET NOT NULL,
                ALTER COLUMN updated_at SET DEFAULT NOW()
        """))

    def add_missing_enum_values(type_name: str, values: list) -> None:
        for val in values:
            exists = conn.execute(text("""
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = :type_name AND e.enumlabel = :val
            """), {"type_name": type_name, "val": val}).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE '{val}'"))

    add_missing_enum_values('experiment_status',
        ['DRAFT', 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'])
    add_missing_enum_values('run_status', ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED'])
    add_missing_enum_values('task_complexity', ['SIMPLE', 'MEDIUM', 'COMPLEX'])

    print("✅ [002] A/B testing, skill system, maintenance config applied")

    # =========================================================================
    # [003-A] Reasoning Traces
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'reasoning_traces' not in existing_tables:
        op.create_table(
            'reasoning_traces',
            sa.Column('id',          sa.String(36),  primary_key=True),
            sa.Column('agentium_id', sa.String(20),  unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),   nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at',  sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at',  sa.DateTime(),  nullable=True),
            sa.Column('trace_id',    sa.String(64),  nullable=False),
            sa.Column('task_id',     sa.String(64),  nullable=False),
            sa.Column('agent_id',    sa.String(32),  nullable=False),
            sa.Column('agent_tier',  sa.Integer(),   nullable=False, server_default='3'),
            sa.Column('incarnation', sa.Integer(),   nullable=False, server_default='1'),
            sa.Column('goal',          sa.Text(), nullable=False),
            sa.Column('goal_restated', sa.Text(), nullable=True),
            sa.Column('plan',            sa.JSON(), nullable=True),
            sa.Column('skills_used',     sa.JSON(), nullable=True),
            sa.Column('context_summary', sa.Text(), nullable=True),
            sa.Column('current_phase',     sa.String(32), nullable=False,
                      server_default='goal_interpretation'),
            sa.Column('final_outcome',     sa.String(16), nullable=True),
            sa.Column('failure_reason',    sa.Text(),     nullable=True),
            sa.Column('validation_passed', sa.Boolean(),  nullable=True),
            sa.Column('validation_notes',  sa.Text(),     nullable=True),
            sa.Column('total_tokens',      sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_duration_ms', sa.Float(),   nullable=False, server_default='0.0'),
            sa.Column('started_at',        sa.DateTime(), nullable=False,
                      server_default=sa.func.now()),
            sa.Column('completed_at',      sa.DateTime(), nullable=True),
        )
        op.create_index('ix_reasoning_traces_trace_id',   'reasoning_traces', ['trace_id'],       unique=True)
        op.create_index('ix_reasoning_traces_task_id',    'reasoning_traces', ['task_id'])
        op.create_index('ix_reasoning_traces_agent_id',   'reasoning_traces', ['agent_id'])
        op.create_index('ix_reasoning_traces_outcome',    'reasoning_traces', ['final_outcome'])
        op.create_index('ix_reasoning_traces_phase',      'reasoning_traces', ['current_phase'])
        op.create_index('ix_reasoning_traces_created_at', 'reasoning_traces', ['created_at'])
        op.create_index('ix_reasoning_traces_validation', 'reasoning_traces', ['validation_passed'])

    if 'reasoning_steps' not in existing_tables:
        op.create_table(
            'reasoning_steps',
            sa.Column('id',          sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),  nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at',  sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at',  sa.DateTime(), nullable=True),
            sa.Column('trace_id',    sa.String(64),
                      sa.ForeignKey('reasoning_traces.trace_id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('step_id',   sa.String(80), nullable=False),
            sa.Column('phase',     sa.String(32), nullable=False),
            sa.Column('sequence',  sa.Integer(),  nullable=False),
            sa.Column('description',  sa.Text(),  nullable=False),
            sa.Column('rationale',    sa.Text(),  nullable=False),
            sa.Column('alternatives', sa.JSON(),  nullable=True),
            sa.Column('inputs',       sa.JSON(),  nullable=True),
            sa.Column('outputs',      sa.JSON(),  nullable=True),
            sa.Column('outcome',      sa.String(16), nullable=False, server_default='pending'),
            sa.Column('error',        sa.Text(),     nullable=True),
            sa.Column('tokens_used',  sa.Integer(),  nullable=False, server_default='0'),
            sa.Column('duration_ms',  sa.Float(),    nullable=False, server_default='0.0'),
            sa.Column('started_at',   sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_reasoning_steps_step_id',           'reasoning_steps', ['step_id'],            unique=True)
        op.create_index('ix_reasoning_steps_trace_id',          'reasoning_steps', ['trace_id'])
        op.create_index('ix_reasoning_steps_phase',             'reasoning_steps', ['phase'])
        op.create_index('ix_reasoning_steps_outcome',           'reasoning_steps', ['outcome'])
        op.create_index('ix_reasoning_steps_trace_id_sequence', 'reasoning_steps', ['trace_id', 'sequence'])

    inspector = Inspector.from_engine(conn)
    task_cols = _col_names(inspector, 'tasks')
    if 'latest_trace_id' not in task_cols:
        op.add_column('tasks', sa.Column('latest_trace_id', sa.String(64), nullable=True))

    # =========================================================================
    # [003-B] Chat performance indexes
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    for idx_name, table, columns, kwargs in [
        ('idx_chat_messages_user_created',  'chat_messages',  ['user_id',         sa.text('created_at DESC')], {'postgresql_using': 'btree'}),
        ('idx_chat_messages_conversation',  'chat_messages',  ['conversation_id', sa.text('created_at DESC')], {'postgresql_using': 'btree'}),
        ('idx_conversations_user_last_msg', 'conversations',  ['user_id',         sa.text('last_message_at DESC')], {'postgresql_using': 'btree'}),
        ('idx_conversations_user_active',   'conversations',  ['user_id', 'is_deleted', 'is_archived'], {'postgresql_using': 'btree'}),
    ]:
        if not _index_exists(inspector, table, idx_name):
            op.create_index(idx_name, table, columns, unique=False, **kwargs)

    # =========================================================================
    # [003-C] Phase 11 Ecosystem — RBAC, federation, plugins, device_tokens
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())
    user_cols = _col_names(inspector, 'users')

    if 'role' not in user_cols:
        op.add_column('users', sa.Column('role', sa.String(30), nullable=False, server_default='observer'))
    if 'delegated_by_id' not in user_cols:
        op.add_column('users', sa.Column('delegated_by_id', sa.String(36), nullable=True))
        op.create_foreign_key('fk_users_delegated_by_id', 'users', 'users', ['delegated_by_id'], ['id'])
    if 'role_expires_at' not in user_cols:
        op.add_column('users', sa.Column('role_expires_at', sa.DateTime(timezone=True), nullable=True))
    if 'last_login_at' not in user_cols:
        op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    if 'delegations' not in existing_tables:
        op.create_table(
            'delegations',
            sa.Column('id',          sa.String(36), primary_key=True),
            sa.Column('grantor_id',  sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('grantee_id',  sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('capabilities',  sa.JSON(),    nullable=False),
            sa.Column('reason',        sa.String(500), nullable=True),
            sa.Column('granted_at',    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at',    sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_at',    sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_emergency',  sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',     sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at',    sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_delegations_grantor_id', 'delegations', ['grantor_id'])
        op.create_index('ix_delegations_grantee_id', 'delegations', ['grantee_id'])

    if 'federated_instances' not in existing_tables:
        op.create_table(
            'federated_instances',
            sa.Column('id',                  sa.String(36),  primary_key=True),
            sa.Column('name',                sa.String(100), nullable=False),
            sa.Column('base_url',            sa.String(255), nullable=False, unique=True),
            sa.Column('shared_secret_hash',  sa.String(255), nullable=False),
            sa.Column('status',              sa.String(20),  nullable=False, server_default='pending'),
            sa.Column('trust_level',         sa.String(20),  nullable=False, server_default='limited'),
            sa.Column('capabilities_shared', sa.JSON(),      nullable=True),
            sa.Column('registered_at',       sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('last_heartbeat_at',   sa.DateTime(timezone=True), nullable=True),
            sa.Column('signing_key',         sa.String(255), nullable=True),  # included upfront
            sa.Column('created_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',           sa.Boolean(),   server_default='true', nullable=False),
            sa.Column('deleted_at',          sa.DateTime(timezone=True), nullable=True),
        )

    if 'federated_tasks' not in existing_tables:
        op.create_table(
            'federated_tasks',
            sa.Column('id',                  sa.String(36), primary_key=True),
            sa.Column('source_instance_id',  sa.String(36), sa.ForeignKey('federated_instances.id'), nullable=True),
            sa.Column('target_instance_id',  sa.String(36), sa.ForeignKey('federated_instances.id'), nullable=True),
            sa.Column('original_task_id',    sa.String(36), nullable=False),
            sa.Column('local_task_id',       sa.String(36), sa.ForeignKey('tasks.id'), nullable=True),
            sa.Column('status',              sa.String(20), nullable=False, server_default='pending'),
            sa.Column('delegated_at',        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('completed_at',        sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',           sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at',          sa.DateTime(timezone=True), nullable=True),
        )

    if 'federated_votes' not in existing_tables:
        op.create_table(
            'federated_votes',
            sa.Column('id',                      sa.String(36), primary_key=True),
            sa.Column('proposal_id',             sa.String(36), nullable=False),
            sa.Column('participating_instances', sa.JSON(),     nullable=True),
            sa.Column('votes',                   sa.JSON(),     nullable=True),
            sa.Column('status',                  sa.String(20), nullable=False, server_default='open'),
            sa.Column('closes_at',               sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at',              sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',              sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',               sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at',              sa.DateTime(timezone=True), nullable=True),
        )

    if 'plugins' not in existing_tables:
        op.create_table(
            'plugins',
            sa.Column('id',                   sa.String(36),  primary_key=True),
            sa.Column('name',                 sa.String(100), nullable=False, unique=True),
            sa.Column('description',          sa.Text(),      nullable=False),
            sa.Column('author',               sa.String(100), nullable=False),
            sa.Column('version',              sa.String(20),  nullable=False),
            sa.Column('plugin_type',          sa.String(50),  nullable=False),
            sa.Column('source_url',           sa.String(255), nullable=True),
            sa.Column('is_verified',          sa.Boolean(),   nullable=False, server_default='false'),
            sa.Column('verification_date',    sa.DateTime(timezone=True), nullable=True),
            sa.Column('install_count',        sa.Integer(),   nullable=False, server_default='0'),
            sa.Column('rating',               sa.Float(),     nullable=False, server_default='0.0'),
            sa.Column('revenue_share_percent',sa.Float(),     nullable=False, server_default='0.0'),
            sa.Column('config_schema',        sa.JSON(),      nullable=True),
            sa.Column('entry_point',          sa.String(255), nullable=False),
            sa.Column('dependencies',         sa.JSON(),      nullable=True),
            sa.Column('status',               sa.String(20),  nullable=False, server_default='draft'),
            sa.Column('submitted_at',         sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('published_at',         sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at',           sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',           sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',            sa.Boolean(),   server_default='true', nullable=False),
            sa.Column('deleted_at',           sa.DateTime(timezone=True), nullable=True),
        )

    if 'plugin_installations' not in existing_tables:
        op.create_table(
            'plugin_installations',
            sa.Column('id',           sa.String(36),  primary_key=True),
            sa.Column('plugin_id',    sa.String(36),  sa.ForeignKey('plugins.id', ondelete='CASCADE'), nullable=False),
            sa.Column('instance_id',  sa.String(100), nullable=False, server_default='local'),
            sa.Column('config',       sa.JSON(),      nullable=True),
            sa.Column('installed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',    sa.Boolean(),   server_default='true', nullable=False),
            sa.Column('deleted_at',   sa.DateTime(timezone=True), nullable=True),
        )

    if 'plugin_reviews' not in existing_tables:
        op.create_table(
            'plugin_reviews',
            sa.Column('id',          sa.String(36),  primary_key=True),
            sa.Column('plugin_id',   sa.String(36),  sa.ForeignKey('plugins.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id',     sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('rating',      sa.Integer(),   nullable=False),
            sa.Column('review_text', sa.String(1000),nullable=True),
            sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active',   sa.Boolean(),   server_default='true', nullable=False),
            sa.Column('deleted_at',  sa.DateTime(timezone=True), nullable=True),
        )

    if 'device_tokens' not in existing_tables:
        op.create_table(
            'device_tokens',
            sa.Column('id',            sa.String(36),  primary_key=True),
            sa.Column('user_id',       sa.String(36),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('platform',      sa.String(20),  nullable=False),
            sa.Column('token',         sa.String(255), nullable=False, unique=True),
            sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('last_used_at',  sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_active',     sa.Boolean(),   nullable=False, server_default='true'),
            sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('deleted_at',    sa.DateTime(timezone=True), nullable=True),
        )

    # =========================================================================
    # [003-D] Notification preferences
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'notification_preferences' not in existing_tables:
        op.create_table(
            'notification_preferences',
            sa.Column('id',                     sa.String(36), primary_key=True),
            sa.Column('user_id',                sa.String(36),
                      sa.ForeignKey('users.id', ondelete='CASCADE'),
                      nullable=False, unique=True),
            sa.Column('votes_enabled',          sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('alerts_enabled',         sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('tasks_enabled',          sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('constitutional_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('quiet_hours_start',      sa.String(5), nullable=True),
            sa.Column('quiet_hours_end',        sa.String(5), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'])

    # =========================================================================
    # [003-G] A/B Testing — unique constraint + index on model_performance_cache
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    if not _constraint_exists(inspector, 'model_performance_cache', 'uq_perf_cache_task_category'):
        conn.execute(sa.text("""
            DELETE FROM model_performance_cache
            WHERE id NOT IN (
                SELECT DISTINCT ON (task_category) id
                FROM model_performance_cache
                ORDER BY task_category, last_updated DESC NULLS LAST
            )
        """))
        op.create_unique_constraint(
            'uq_perf_cache_task_category', 'model_performance_cache', ['task_category'],
        )
    if not _index_exists(inspector, 'model_performance_cache', 'ix_perf_cache_last_updated'):
        op.create_index('ix_perf_cache_last_updated', 'model_performance_cache', ['last_updated'])

    # =========================================================================
    # [003-H] Outbound Webhooks
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'webhook_subscriptions' not in existing_tables:
        op.create_table(
            'webhook_subscriptions',
            sa.Column('id',          sa.String(36),  primary_key=True),
            sa.Column('user_id',     sa.String(36),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('url',         sa.String(500), nullable=False),
            sa.Column('secret',      sa.String(255), nullable=False),
            sa.Column('description', sa.String(500), nullable=True),
            sa.Column('events',      sa.JSON(),      nullable=False),
            sa.Column('is_active',   sa.Boolean(),   nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at',  sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_webhook_subscriptions_user_id',   'webhook_subscriptions', ['user_id'])
        op.create_index('ix_webhook_subscriptions_is_active', 'webhook_subscriptions', ['is_active'])

    if 'webhook_delivery_logs' not in existing_tables:
        op.create_table(
            'webhook_delivery_logs',
            sa.Column('id',               sa.String(36), primary_key=True),
            sa.Column('subscription_id',  sa.String(36),
                      sa.ForeignKey('webhook_subscriptions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('delivery_id',      sa.String(36), nullable=False, unique=True),
            sa.Column('event_type',       sa.String(50), nullable=False),
            sa.Column('payload',          sa.JSON(),     nullable=False),
            sa.Column('status_code',      sa.Integer(),  nullable=True),
            sa.Column('response_body',    sa.Text(),     nullable=True),
            sa.Column('attempts',         sa.Integer(),  nullable=False, server_default='0'),
            sa.Column('max_attempts',     sa.Integer(),  nullable=False, server_default='5'),
            sa.Column('delivered_at',     sa.DateTime(timezone=True), nullable=True),
            sa.Column('next_retry_at',    sa.DateTime(timezone=True), nullable=True),
            sa.Column('failed_at',        sa.DateTime(timezone=True), nullable=True),
            sa.Column('error',            sa.Text(),     nullable=True),
            sa.Column('created_at',       sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_webhook_delivery_logs_subscription_id', 'webhook_delivery_logs', ['subscription_id'])
        op.create_index('ix_webhook_delivery_logs_event_type',      'webhook_delivery_logs', ['event_type'])
        op.create_index('ix_webhook_delivery_logs_next_retry',      'webhook_delivery_logs', ['next_retry_at'])

    # =========================================================================
    # [003-I] Composite index on user_model_configs
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    if not _index_exists(inspector, 'user_model_configs', 'ix_user_model_configs_user_default'):
        op.create_index('ix_user_model_configs_user_default', 'user_model_configs',
                        ['user_id', 'is_default'], unique=False)

    # =========================================================================
    # [003-J] Workflows — workflow_executions + workflow_subtasks + tasks columns
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'workflows' not in existing_tables:
        op.create_table(
            'workflows',
            sa.Column('id',          sa.String(36),  primary_key=True),
            sa.Column('agentium_id', sa.String(20),  unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),   nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(),  nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at',  sa.DateTime(),  nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at',  sa.DateTime(),  nullable=True),
            sa.Column('name',                 sa.String(100), nullable=False),
            sa.Column('description',          sa.Text(),      nullable=True),
            sa.Column('template_json',        sa.JSON(),      nullable=False, server_default='{}'),
            sa.Column('version',              sa.Integer(),   nullable=False, server_default='1'),
            sa.Column('created_by_agent_id',  sa.String(36),
                      sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('schedule_cron',        sa.String(100), nullable=True),
        )
        op.create_index('ix_workflows_created_by_agent_id', 'workflows', ['created_by_agent_id'])

    if 'workflow_executions' not in existing_tables:
        op.create_table(
            'workflow_executions',
            sa.Column('id',         sa.String(36), primary_key=True),
            sa.Column('is_active',  sa.Boolean(),  nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('workflow_id',         sa.String(36),  nullable=False),
            sa.Column('original_message',    sa.Text(),      nullable=False),
            sa.Column('status',              sa.String(32),  nullable=False, server_default='pending'),
            sa.Column('context_data',        sa.JSON(),      nullable=False, server_default='{}'),
            sa.Column('error',               sa.Text(),      nullable=True),
            sa.Column('created_by',          sa.String(128), nullable=True),
            sa.Column('completed_at',        sa.DateTime(),  nullable=True),
            sa.Column('current_step_index',  sa.Integer(),   nullable=False, server_default='0'),
            sa.Column('started_at',          sa.DateTime(),  nullable=True),
            sa.Column('triggered_by',        sa.String(100), nullable=True),
        )
        op.create_index('ix_workflow_executions_status', 'workflow_executions', ['status'])
        op.execute(
            "ALTER TABLE workflow_executions "
            "ADD CONSTRAINT fk_workflow_executions_workflow_id "
            "FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE"
        )
        op.create_index('ix_workflow_executions_workflow_id', 'workflow_executions', ['workflow_id'])

    if 'workflow_subtasks' not in existing_tables:
        op.create_table(
            'workflow_subtasks',
            sa.Column('id',         sa.String(36), primary_key=True),
            sa.Column('is_active',  sa.Boolean(),  nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('workflow_id',
                      sa.String(36),
                      sa.ForeignKey('workflows.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('step_index',           sa.Integer(),   nullable=False, server_default='0'),
            sa.Column('intent',               sa.String(128), nullable=False),
            sa.Column('params',               sa.JSON(),      nullable=False, server_default='{}'),
            sa.Column('depends_on',           sa.JSON(),      nullable=False, server_default='[]'),
            sa.Column('status',               sa.String(32),  nullable=False, server_default='pending'),
            sa.Column('result',               sa.JSON(),      nullable=True),
            sa.Column('error',                sa.Text(),      nullable=True),
            sa.Column('celery_task_id',       sa.String(256), nullable=True),
            sa.Column('schedule_offset_days', sa.Integer(),   nullable=False, server_default='0'),
            sa.Column('scheduled_for',        sa.DateTime(),  nullable=True),
            sa.Column('completed_at',         sa.DateTime(),  nullable=True),
        )
        op.create_index('ix_workflow_subtasks_workflow_id', 'workflow_subtasks', ['workflow_id'])
        op.create_index('ix_workflow_subtasks_status',      'workflow_subtasks', ['status'])

    # New columns on tasks (from 006_workflow)
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS workflow_id    VARCHAR(64)  NULL")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS context_data   JSON         NULL")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(256) NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_workflow_id ON tasks (workflow_id)")

    # =========================================================================
    # [003-M] Task Delegation Engine
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'task_dependencies' not in existing_tables:
        op.create_table(
            'task_dependencies',
            sa.Column('id',          sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),  nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at',  sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('deleted_at',  sa.DateTime(), nullable=True),
            sa.Column('parent_task_id',   sa.String(36),
                      sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('child_task_id',    sa.String(36),
                      sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('dependency_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('status',           sa.String(20), nullable=False, server_default='pending'),
        )
        op.create_index('ix_task_deps_parent', 'task_dependencies', ['parent_task_id'])
        op.create_index('ix_task_deps_child',  'task_dependencies', ['child_task_id'])
        op.create_index('ix_task_deps_order',  'task_dependencies', ['parent_task_id', 'dependency_order'])

    inspector = Inspector.from_engine(conn)
    task_cols = _col_names(inspector, 'tasks')
    if 'complexity_score' not in task_cols:
        op.add_column('tasks', sa.Column('complexity_score', sa.Integer(), nullable=True))
    if 'escalation_timeout_seconds' not in task_cols:
        op.add_column('tasks', sa.Column('escalation_timeout_seconds', sa.Integer(),
                                         nullable=False, server_default='300'))
    if 'delegation_metadata' not in task_cols:
        op.add_column('tasks', sa.Column('delegation_metadata', sa.JSON(), nullable=True))

    # =========================================================================
    # [003-N] Self-Healing — agents.last_heartbeat_at
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    agent_cols = _col_names(inspector, 'agents')
    if 'last_heartbeat_at' not in agent_cols:
        op.add_column('agents', sa.Column('last_heartbeat_at', sa.DateTime(), nullable=True))
        op.create_index('ix_agents_last_heartbeat_at', 'agents', ['last_heartbeat_at'])

    print("✅ [003] Reasoning traces, RBAC, federation, webhooks, workflows applied")

    # =========================================================================
    # [004] EVENT TRIGGERS & EVENT LOGS
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'event_triggers' not in existing_tables:
        op.create_table(
            'event_triggers',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False, index=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('trigger_type', sa.Enum(
                'webhook', 'schedule', 'threshold', 'api_poll',
                name='triggertype', create_type=True,
            ), nullable=False),
            sa.Column('config', sa.JSON, nullable=False, server_default='{}'),
            sa.Column('target_workflow_id', sa.String(36),
                      sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True),
            sa.Column('target_agent_id', sa.String(36),
                      sa.ForeignKey('agents.id', ondelete='SET NULL'), nullable=True),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('last_fired_at', sa.DateTime, nullable=True),
            sa.Column('fire_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('max_fires_per_minute', sa.Integer, nullable=False, server_default='10'),
            sa.Column('pause_duration_seconds', sa.Integer, nullable=False, server_default='300'),
            sa.Column('paused_until', sa.DateTime, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime, nullable=True),
        )
        op.create_index('ix_event_triggers_trigger_type', 'event_triggers', ['trigger_type'])
        op.create_index('ix_event_triggers_is_active',    'event_triggers', ['is_active'])

    if 'event_logs' not in existing_tables:
        op.create_table(
            'event_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(10), unique=True, nullable=False, index=True),
            sa.Column('trigger_id', sa.String(36),
                      sa.ForeignKey('event_triggers.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('event_payload', sa.JSON, nullable=False, server_default='{}'),
            sa.Column('status', sa.Enum(
                'processed', 'dead_letter', 'duplicate',
                name='eventlogstatus', create_type=True,
            ), nullable=False),
            sa.Column('correlation_id', sa.String(36), nullable=True, index=True),
            sa.Column('error', sa.Text, nullable=True),
            sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime, nullable=True),
        )
        op.create_index('ix_event_logs_status', 'event_logs', ['status'])

    print("✅ [004] event_triggers & event_logs applied")

    # =========================================================================
    # [005] SPEAKER PROFILES
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'speaker_profiles' not in existing_tables:
        op.create_table(
            'speaker_profiles',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('user_id', sa.String(length=36), nullable=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('embedding', sa.JSON(), nullable=False),
            sa.Column('sample_count', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('enrolled_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_speaker_profiles_id'),      'speaker_profiles', ['id'],      unique=False)
        op.create_index(op.f('ix_speaker_profiles_user_id'), 'speaker_profiles', ['user_id'], unique=False)

    print("✅ [005] speaker_profiles applied")

    # =========================================================================
    # [006] WAIT CONDITIONS (waitstrategy / waitconditionstatus enums)
    # =========================================================================
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'waitstrategy') THEN
                CREATE TYPE waitstrategy AS ENUM
                    ('http_poll','redis_key','timeout','webhook','manual');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'waitconditionstatus') THEN
                CREATE TYPE waitconditionstatus AS ENUM
                    ('pending','active','resolved','expired','cancelled');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'waiting';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'checkpointphase') THEN
                ALTER TYPE checkpointphase ADD VALUE IF NOT EXISTS 'wait_entered';
            END IF;
        END $$;
    """)

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'wait_conditions' not in existing_tables:
        op.create_table(
            "wait_conditions",
            sa.Column("id",          sa.String(36),  nullable=False, primary_key=True),
            sa.Column("agentium_id", sa.String(20),  nullable=True,  unique=True),
            sa.Column("created_at",  sa.DateTime(),  nullable=True),
            sa.Column("updated_at",  sa.DateTime(),  nullable=True),
            sa.Column("deleted_at",  sa.DateTime(),  nullable=True),
            sa.Column("is_active",   sa.Boolean(),   nullable=True,  server_default="true"),
            sa.Column("task_id", sa.String(36),
                      sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("strategy", wait_strategy_enum, nullable=False),
            sa.Column("status", wait_condition_status_enum,
                      nullable=False, server_default="pending"),
            sa.Column("config",                postgresql.JSON(), nullable=False,
                      server_default=sa.text("'{}'::json")),
            sa.Column("max_attempts",          sa.Integer(), nullable=False, server_default="60"),
            sa.Column("attempt_count",         sa.Integer(), nullable=False, server_default="0"),
            sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("expires_at",            sa.DateTime(), nullable=True),
            sa.Column("resolved_at",           sa.DateTime(), nullable=True),
            sa.Column("resolution_data",       postgresql.JSON(), nullable=True),
            sa.Column("failure_reason",        sa.Text(), nullable=True),
            sa.Column("created_by_agent_id",   sa.String(36), nullable=True),
        )
        op.create_index("ix_wait_conditions_task_id", "wait_conditions", ["task_id"])
        op.create_index("ix_wait_conditions_status",  "wait_conditions", ["status"])

    print("✅ [006] wait_conditions applied")

    # =========================================================================
    # [007] CITATION EDGES
    # =========================================================================
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'citation_edges' not in existing_tables:
        op.create_table(
            "citation_edges",
            sa.Column("id",              sa.String(36),  nullable=False, primary_key=True),
            sa.Column("source_doc_id",   sa.String(255), nullable=False),
            sa.Column("cited_by_doc_id", sa.String(255), nullable=False),
            sa.Column("task_id",         sa.String(36),
                      sa.ForeignKey("tasks.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("collection_key",  sa.String(64),  nullable=False, server_default=""),
            sa.Column("relevance_score", sa.Float(),      nullable=False, server_default="0.0"),
            sa.Column("created_at",      sa.DateTime(),   nullable=False,
                      server_default=sa.text("NOW()")),
        )
        op.create_index("ix_citation_edges_source_doc_id",   "citation_edges", ["source_doc_id"])
        op.create_index("ix_citation_edges_cited_by_doc_id", "citation_edges", ["cited_by_doc_id"])
        op.create_index("ix_citation_edges_task_id",         "citation_edges", ["task_id"])
        op.create_index("ix_citation_edges_created_at",      "citation_edges", ["created_at"])
        op.create_index(
            "ix_citation_edges_source_collection",
            "citation_edges",
            ["source_doc_id", "collection_key"],
        )

    print("✅ [007] citation_edges applied")
    print("✅ 000_combined_migration upgrade complete")


# =============================================================================
# DOWNGRADE
# =============================================================================

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🔄 Downgrading 000_combined_migration ...")

    # ── [007] Citation Edges ──────────────────────────────────────────────────
    if 'citation_edges' in existing_tables:
        op.drop_index("ix_citation_edges_source_collection", table_name="citation_edges")
        op.drop_index("ix_citation_edges_created_at",        table_name="citation_edges")
        op.drop_index("ix_citation_edges_task_id",           table_name="citation_edges")
        op.drop_index("ix_citation_edges_cited_by_doc_id",   table_name="citation_edges")
        op.drop_index("ix_citation_edges_source_doc_id",     table_name="citation_edges")
        op.drop_table("citation_edges")

    # ── [006] Wait Conditions ─────────────────────────────────────────────────
    if 'wait_conditions' in existing_tables:
        op.drop_index("ix_wait_conditions_status",  table_name="wait_conditions")
        op.drop_index("ix_wait_conditions_task_id", table_name="wait_conditions")
        op.drop_table("wait_conditions")
    op.execute("DROP TYPE IF EXISTS waitconditionstatus")
    op.execute("DROP TYPE IF EXISTS waitstrategy")

    # ── [005] Speaker Profiles ────────────────────────────────────────────────
    if 'speaker_profiles' in existing_tables:
        op.drop_index(op.f('ix_speaker_profiles_user_id'), table_name='speaker_profiles')
        op.drop_index(op.f('ix_speaker_profiles_id'),      table_name='speaker_profiles')
        op.drop_table('speaker_profiles')

    # ── [004] Event Logs & Triggers ───────────────────────────────────────────
    if 'event_logs' in existing_tables:
        op.drop_table('event_logs')
    if 'event_triggers' in existing_tables:
        op.drop_table('event_triggers')
    sa.Enum(name='eventlogstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='triggertype').drop(op.get_bind(), checkfirst=True)

    # ── [003] Consolidated ────────────────────────────────────────────────────
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())
    agent_cols = _col_names(inspector, 'agents')
    if 'last_heartbeat_at' in agent_cols:
        op.drop_index('ix_agents_last_heartbeat_at', table_name='agents')
        op.drop_column('agents', 'last_heartbeat_at')

    task_cols = _col_names(inspector, 'tasks')
    for col in ('delegation_metadata', 'escalation_timeout_seconds', 'complexity_score'):
        if col in task_cols:
            op.drop_column('tasks', col)

    if 'task_dependencies' in existing_tables:
        op.drop_index('ix_task_deps_order',  table_name='task_dependencies')
        op.drop_index('ix_task_deps_child',  table_name='task_dependencies')
        op.drop_index('ix_task_deps_parent', table_name='task_dependencies')
        op.drop_table('task_dependencies')

    if 'webhook_delivery_logs' in existing_tables:
        op.drop_table('webhook_delivery_logs')
    if 'webhook_subscriptions' in existing_tables:
        op.drop_table('webhook_subscriptions')

    op.execute("DROP INDEX IF EXISTS ix_tasks_workflow_id")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS celery_task_id")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS context_data")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS workflow_id")

    if 'workflow_subtasks' in existing_tables:
        op.drop_index('ix_workflow_subtasks_status',      table_name='workflow_subtasks')
        op.drop_index('ix_workflow_subtasks_workflow_id', table_name='workflow_subtasks')
        op.drop_table('workflow_subtasks')

    if 'workflow_executions' in existing_tables:
        fks = inspector.get_foreign_keys('workflow_executions')
        for fk in fks:
            if fk.get('name') == 'fk_workflow_executions_workflow_id':
                op.drop_constraint('fk_workflow_executions_workflow_id',
                                   'workflow_executions', type_='foreignkey')
        op.drop_index('ix_workflow_executions_status',      table_name='workflow_executions')
        op.drop_index('ix_workflow_executions_workflow_id', table_name='workflow_executions')
        op.drop_table('workflow_executions')

    if 'workflows' in existing_tables:
        try:
            op.drop_index('ix_workflows_created_by_agent_id', table_name='workflows')
        except Exception:
            pass
        op.drop_table('workflows')

    if 'notification_preferences' in existing_tables:
        op.drop_table('notification_preferences')

    for tbl in ('device_tokens', 'plugin_reviews', 'plugin_installations', 'plugins',
                'federated_votes', 'federated_tasks', 'federated_instances', 'delegations'):
        inspector = Inspector.from_engine(conn)
        existing_tables = set(inspector.get_table_names())
        if tbl in existing_tables:
            op.drop_table(tbl)

    inspector = Inspector.from_engine(conn)
    user_cols = _col_names(inspector, 'users')
    if 'role_expires_at' in user_cols:
        op.drop_column('users', 'role_expires_at')
    if 'delegated_by_id' in user_cols:
        try:
            op.drop_constraint('fk_users_delegated_by_id', 'users', type_='foreignkey')
        except Exception:
            pass
        op.drop_column('users', 'delegated_by_id')
    if 'last_login_at' in user_cols:
        op.drop_column('users', 'last_login_at')
    if 'role' in user_cols:
        op.drop_column('users', 'role')

    inspector = Inspector.from_engine(conn)
    if _index_exists(inspector, 'user_model_configs', 'ix_user_model_configs_user_default'):
        op.drop_index('ix_user_model_configs_user_default', table_name='user_model_configs')

    if 'skill_submissions' in existing_tables:
        for idx in ('ix_skill_submissions_submitted_by', 'ix_skill_submissions_status',
                    'ix_skill_submissions_skill_id', 'ix_skill_submissions_submission_id'):
            try:
                op.drop_index(idx, table_name='skill_submissions')
            except Exception:
                pass
        op.drop_table('skill_submissions')

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())
    if 'skills' in existing_tables:
        for idx in ('ix_skills_domain_usage', 'ix_skills_creator_id',
                    'ix_skills_verification_usage', 'ix_skills_skill_id'):
            try:
                op.drop_index(idx, table_name='skills')
            except Exception:
                pass
        op.drop_table('skills')

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())
    task_cols = _col_names(inspector, 'tasks')
    if 'latest_trace_id' in task_cols:
        op.drop_column('tasks', 'latest_trace_id')

    if 'reasoning_steps' in existing_tables:
        for idx in ('ix_reasoning_steps_trace_id_sequence', 'ix_reasoning_steps_outcome',
                    'ix_reasoning_steps_phase', 'ix_reasoning_steps_trace_id',
                    'ix_reasoning_steps_step_id'):
            try:
                op.drop_index(idx, table_name='reasoning_steps')
            except Exception:
                pass
        op.drop_table('reasoning_steps')

    if 'reasoning_traces' in existing_tables:
        for idx in ('ix_reasoning_traces_validation', 'ix_reasoning_traces_created_at',
                    'ix_reasoning_traces_phase', 'ix_reasoning_traces_outcome',
                    'ix_reasoning_traces_agent_id', 'ix_reasoning_traces_task_id',
                    'ix_reasoning_traces_trace_id'):
            try:
                op.drop_index(idx, table_name='reasoning_traces')
            except Exception:
                pass
        op.drop_table('reasoning_traces')

    # ── [002] A/B testing, skill system ───────────────────────────────────────
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    iv_columns = {col['name'] for col in inspector.get_columns('individual_votes')}
    if 'updated_at' in iv_columns:
        op.drop_column('individual_votes', 'updated_at')

    if 'db_maintenance_config' in existing_tables:
        op.drop_table('db_maintenance_config')

    op.execute("DROP FUNCTION IF EXISTS create_backup_sql()")
    op.execute("DROP FUNCTION IF EXISTS backup_table_to_json(text)")

    for table in ['model_performance_cache', 'experiment_results', 'experiment_runs', 'experiments']:
        if table in existing_tables:
            try:
                op.drop_table(table)
            except Exception:
                pass

    for enum_type in ['task_complexity', 'run_status', 'experiment_status']:
        op.execute(f"DROP TYPE IF EXISTS {enum_type} CASCADE")

    # ── [001] Base schema ─────────────────────────────────────────────────────
    tables_to_drop = [
        'user_preference_history', 'user_preferences',
        'mcp_tools',
        'sandboxes', 'remote_executions',
        'execution_checkpoints',
        'scheduled_task_executions', 'scheduled_tasks',
        'tool_marketplace_listings', 'tool_usage_logs', 'tool_versions', 'tool_staging',
        'critique_reviews',
        'monitoring_alerts', 'performance_metrics', 'task_verifications',
        'violation_reports', 'agent_health_reports',
        'chat_messages', 'conversations',
        'model_usage_logs', 'system_settings',
        'external_messages', 'external_channels', 'channels',
        'audit_logs',
        'individual_votes', 'voting_records',
        'amendment_votings',
        'task_audit_logs', 'task_events', 'task_deliberations',
        'subtasks', 'tasks',
        'constitutions',
        'critic_agents', 'task_agents', 'lead_agents', 'council_members', 'head_of_council',
        'agents', 'ethos', 'user_model_configs', 'users',
    ]
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())
    for table in tables_to_drop:
        if table in existing_tables:
            try:
                op.drop_table(table)
            except Exception as e:
                print(f"  Note: could not drop {table}: {e}")

    for enum_type in ('taskstatus', 'tasktype', 'taskpriority'):
        try:
            op.execute(f"DROP TYPE IF EXISTS {enum_type} CASCADE")
        except Exception as e:
            print(f"  Note: could not drop enum {enum_type}: {e}")

    print("✅ 000_combined_migration downgrade complete")
