"""Initial schema for Agentium

Revision ID: 001
Revises: 
Create Date: 2024-02-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('email', sa.String(100), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('is_admin', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_table(
        'scheduled_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),  # R0001 format
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cron_expression', sa.String(100), nullable=False),  # "0 9 * * *"
        sa.Column('task_payload', sa.Text(), nullable=False),  # JSON: {action, params, constraints}
        sa.Column('owner_agentium_id', sa.String(10), nullable=False, default='00001'),  # Head 00001 owns all schedules
        sa.Column('executing_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),  # Current 3xxxx running it
        sa.Column('status', sa.String(20), default='active'),  # active, paused, completed, error
        sa.Column('priority', sa.Integer(), default=1),
        sa.Column('last_execution_at', sa.DateTime(), nullable=True),
        sa.Column('next_execution_at', sa.DateTime(), nullable=True),
        sa.Column('execution_count', sa.Integer(), default=0),
        sa.Column('failure_count', sa.Integer(), default=0),
        sa.Column('max_retries', sa.Integer(), default=3),
        sa.Column('timezone', sa.String(50), default='UTC'),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_scheduled_next_run', 'scheduled_tasks', ['next_execution_at'])
    op.create_index('idx_scheduled_owner', 'scheduled_tasks', ['owner_agentium_id'])
    op.create_index('idx_scheduled_status', 'scheduled_tasks', ['status'])
    
    # Scheduled Task Executions (History of runs)
    op.create_table(
        'scheduled_task_executions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('scheduled_task_id', sa.String(36), sa.ForeignKey('scheduled_tasks.id')),
        sa.Column('execution_agentium_id', sa.String(10), nullable=False),  # Which 3xxxx executed it
        sa.Column('execution_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('started_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), default='running'),  # running, success, failed, timeout
        sa.Column('result_payload', sa.Text(), nullable=True),  # JSON result
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_number', sa.Integer(), default=0),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    op.create_index('idx_sched_exec_task', 'scheduled_task_executions', ['scheduled_task_id'])
    op.create_index('idx_sched_exec_time', 'scheduled_task_executions', ['started_at'])

    # User model configs
    op.create_table(
        'user_model_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('config_name', sa.String(100), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('default_model', sa.String(50), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('base_url', sa.String(255), nullable=True),
        sa.Column('temperature', sa.Float(), default=0.7),
        sa.Column('max_tokens', sa.Integer(), default=2048),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Constitutions
    op.create_table(
        'constitutions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
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
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_constitution_version', 'constitutions', ['version'])
    op.create_index('idx_constitution_version_number', 'constitutions', ['version_number'])
    op.create_index('idx_constitution_active', 'constitutions', ['is_active'])
    op.create_index('idx_constitution_effective', 'constitutions', ['effective_date'])
    
    # Ethos
    op.create_table(
        'ethos',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=True),
        sa.Column('agent_type', sa.String(20), nullable=False),
        sa.Column('mission_statement', sa.Text(), nullable=False),
        sa.Column('core_values', sa.Text(), nullable=False),
        sa.Column('behavioral_rules', sa.Text(), nullable=False),
        sa.Column('restrictions', sa.Text(), nullable=False),
        sa.Column('capabilities', sa.Text(), nullable=False),
        sa.Column('created_by_agentium_id', sa.String(10), nullable=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('agent_id', sa.String(36), nullable=False),
        sa.Column('verified_by_agentium_id', sa.String(10), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), default=False),
        sa.Column('last_updated_by_agent', sa.Boolean(), default=False),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Agents (base table)
    op.create_table(
        'agents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('agent_type', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('incarnation_number', sa.Integer(), default=1),
        sa.Column('parent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('status', sa.String(20), default='initializing'),
        sa.Column('terminated_at', sa.DateTime(), nullable=True),
        sa.Column('termination_reason', sa.Text(), nullable=True),
        sa.Column('preferred_config_id', sa.String(36), sa.ForeignKey('user_model_configs.id'), nullable=True),
        sa.Column('system_prompt_override', sa.Text(), nullable=True),
        sa.Column('ethos_id', sa.String(36), sa.ForeignKey('ethos.id'), nullable=True),
        sa.Column('constitution_version', sa.String(10), nullable=True),
        sa.Column('spawned_at_task_count', sa.Integer(), default=0),
        sa.Column('tasks_completed', sa.Integer(), default=0),
        sa.Column('tasks_failed', sa.Integer(), default=0),
        sa.Column('current_task_id', sa.String(36), nullable=True),
        sa.Column('is_persistent', sa.Boolean(), default=False),
        sa.Column('idle_mode_enabled', sa.Boolean(), default=False),
        sa.Column('last_idle_action_at', sa.DateTime(), nullable=True),
        sa.Column('idle_task_count', sa.Integer(), default=0),
        sa.Column('idle_tokens_saved', sa.Integer(), default=0),
        sa.Column('current_idle_task_id', sa.String(36), nullable=True),
        sa.Column('persistent_role', sa.String(50), nullable=True),
        sa.Column('last_constitution_read_at', sa.DateTime(), nullable=True),
        sa.Column('constitution_read_count', sa.Integer(), default=0),
        sa.Column('ethos_last_read_at', sa.DateTime(), nullable=True),
        sa.Column('ethos_action_pending', sa.Boolean(), default=False),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_agent_type_status', 'agents', ['agent_type', 'status'])
    op.create_index('idx_parent_id', 'agents', ['parent_id'])
    op.create_index('idx_agents_is_persistent', 'agents', ['is_persistent'])
    op.create_index('idx_agents_last_idle', 'agents', ['last_idle_action_at'])
    
    # Head of Council (inherits from agents)
    op.create_table(
        'head_of_council',
        sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
        sa.Column('emergency_override_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_constitution_update', sa.DateTime(), nullable=True),
    )
    
    # Council Members
    op.create_table(
        'council_members',
        sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
        sa.Column('specialization', sa.String(50), nullable=True),
        sa.Column('votes_participated', sa.Integer(), default=0),
        sa.Column('votes_abstained', sa.Integer(), default=0),
    )
    
    # Lead Agents
    op.create_table(
        'lead_agents',
        sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
        sa.Column('team_size', sa.Integer(), default=0),
        sa.Column('max_team_size', sa.Integer(), default=10),
        sa.Column('department', sa.String(50), nullable=True),
        sa.Column('spawn_threshold', sa.Integer(), default=5),
    )
    
    # Task Agents
    op.create_table(
        'task_agents',
        sa.Column('id', sa.String(36), sa.ForeignKey('agents.id'), primary_key=True),
        sa.Column('assigned_tools', sa.Text(), nullable=True),
        sa.Column('execution_timeout', sa.Integer(), default=300),
        sa.Column('sandbox_enabled', sa.Boolean(), default=True),
    )
    
    # Tasks
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('priority', sa.Integer(), default=1),
        sa.Column('assigned_to_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # SubTasks
    op.create_table(
        'subtasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id')),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('assigned_to_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('execution_order', sa.Integer(), default=0),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Amendment Voting
    op.create_table(
        'amendment_votings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('constitution_id', sa.String(36), sa.ForeignKey('constitutions.id')),
        sa.Column('proposed_by_agentium_id', sa.String(10), nullable=False),
        sa.Column('proposed_changes', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), default='proposed'),
        sa.Column('votes_required', sa.Integer(), default=3),
        sa.Column('votes_for', sa.Integer(), default=0),
        sa.Column('votes_against', sa.Integer(), default=0),
        sa.Column('votes_abstain', sa.Integer(), default=0),
        sa.Column('voting_started_at', sa.DateTime(), nullable=True),
        sa.Column('voting_ended_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by_agentium_id', sa.String(10), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_amendment_status', 'amendment_votings', ['status'])
    op.create_index('idx_amendment_constitution', 'amendment_votings', ['constitution_id'])
    
    # Individual Votes
    op.create_table(
        'individual_votes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('amendment_voting_id', sa.String(36), sa.ForeignKey('amendment_votings.id')),
        sa.Column('voter_agentium_id', sa.String(10), nullable=False),
        sa.Column('vote', sa.String(10), nullable=False),  # for, against, abstain
        sa.Column('voted_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    
    # Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.String(50), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('target_type', sa.String(30), nullable=True),
        sa.Column('target_id', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('before_state', sa.Text(), nullable=True),
        sa.Column('after_state', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('session_id', sa.String(36), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    op.create_index('idx_audit_actor', 'audit_logs', ['actor_type', 'actor_id'])
    op.create_index('idx_audit_target', 'audit_logs', ['target_type', 'target_id'])
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'])
    
    # Channels
    op.create_table(
        'channels',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('channel_type', sa.String(20), nullable=False),  # slack, discord, etc
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('is_active', sa.String(1), default='Y'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    # Order matters for foreign keys
    op.drop_table('channels')
    op.drop_table('audit_logs')
    op.drop_table('individual_votes')
    op.drop_table('amendment_votings')
    op.drop_table('subtasks')
    op.drop_table('tasks')
    op.drop_table('task_agents')
    op.drop_table('lead_agents')
    op.drop_table('council_members')
    op.drop_table('head_of_council')
    op.drop_table('agents')
    op.drop_table('ethos')
    op.drop_table('constitutions')
    op.drop_table('user_model_configs')
    op.drop_table('users')
    op.drop_table('scheduled_task_executions')
    op.drop_table('scheduled_tasks')