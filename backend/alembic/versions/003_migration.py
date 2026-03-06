"""Combined Migration: 003 through 009

Revision ID: 003_migration
Revises: 002_migration
Create Date: 2026-03-06

What this migration does
─────────────────────────
003  reasoning_traces, reasoning_steps tables; tasks.latest_trace_id
004  Chat performance indexes (chat_messages, conversations)
005  Ecosystem Expansion (Phase 11): RBAC columns on users, delegations,
     federated_instances, federated_tasks, federated_votes,
     plugins, plugin_installations, plugin_reviews, device_tokens
006  notification_preferences table; device_tokens.is_active backfill
007  audit_logs.screenshot_url; critique_reviews.learning_extracted
008  federated_instances.signing_key (HMAC); federated_tasks.status check
009  A/B testing tables (experiments, experiment_runs, experiment_results,
     model_performance_cache) + indexes + schema hardening
"""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.engine.reflection import Inspector

revision = '003_migration'
down_revision = '002_migration'
branch_labels = None
depends_on = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _index_exists(inspector: Inspector, table: str, index_name: str) -> bool:
    """Return True if *index_name* already exists on *table*."""
    return any(
        idx['name'] == index_name
        for idx in inspector.get_indexes(table)
    )


def _constraint_exists(inspector: Inspector, table: str, constraint_name: str) -> bool:
    """Return True if a unique constraint with *constraint_name* exists on *table*."""
    try:
        return any(
            uc.get('name') == constraint_name
            for uc in inspector.get_unique_constraints(table)
        )
    except Exception:
        return False


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🚀 Starting combined migration 003_migration (003–009)...")

    # =========================================================================
    # 003 — Reasoning Trace tables
    # =========================================================================
    print("\n--- 003: Reasoning Traces ---")

    if 'reasoning_traces' not in existing_tables:
        op.create_table(
            'reasoning_traces',
            # ── BaseEntity ────────────────────────────────────────────────────
            sa.Column('id',          sa.String(36),  primary_key=True),
            sa.Column('agentium_id', sa.String(20),  unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),   nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at',  sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at',  sa.DateTime(),  nullable=True),
            # ── Identity ──────────────────────────────────────────────────────
            sa.Column('trace_id',    sa.String(64),  nullable=False),
            sa.Column('task_id',     sa.String(64),  nullable=False),
            sa.Column('agent_id',    sa.String(32),  nullable=False),
            sa.Column('agent_tier',  sa.Integer(),   nullable=False, server_default='3'),
            sa.Column('incarnation', sa.Integer(),   nullable=False, server_default='1'),
            # ── Goal ──────────────────────────────────────────────────────────
            sa.Column('goal',          sa.Text(), nullable=False),
            sa.Column('goal_restated', sa.Text(), nullable=True),
            # ── Plan & context ────────────────────────────────────────────────
            sa.Column('plan',            sa.JSON(), nullable=True),
            sa.Column('skills_used',     sa.JSON(), nullable=True),
            sa.Column('context_summary', sa.Text(), nullable=True),
            # ── Phase & outcome ───────────────────────────────────────────────
            sa.Column('current_phase',     sa.String(32), nullable=False,
                      server_default='goal_interpretation'),
            sa.Column('final_outcome',     sa.String(16), nullable=True),
            sa.Column('failure_reason',    sa.Text(),     nullable=True),
            sa.Column('validation_passed', sa.Boolean(),  nullable=True),
            sa.Column('validation_notes',  sa.Text(),     nullable=True),
            # ── Timing & tokens ───────────────────────────────────────────────
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
        print("  ✅ Created reasoning_traces table")
    else:
        print("  ℹ️  reasoning_traces already exists")

    if 'reasoning_steps' not in existing_tables:
        op.create_table(
            'reasoning_steps',
            # ── BaseEntity ────────────────────────────────────────────────────
            sa.Column('id',          sa.String(36), primary_key=True),
            sa.Column('agentium_id', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active',   sa.Boolean(),  nullable=False, server_default='true'),
            sa.Column('created_at',  sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at',  sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('deleted_at',  sa.DateTime(), nullable=True),
            # ── Parent ────────────────────────────────────────────────────────
            sa.Column('trace_id',    sa.String(64),
                      sa.ForeignKey('reasoning_traces.trace_id', ondelete='CASCADE'),
                      nullable=False),
            # ── Identity ──────────────────────────────────────────────────────
            sa.Column('step_id',   sa.String(80), nullable=False),
            sa.Column('phase',     sa.String(32), nullable=False),
            sa.Column('sequence',  sa.Integer(),  nullable=False),
            # ── Content ───────────────────────────────────────────────────────
            sa.Column('description',  sa.Text(),  nullable=False),
            sa.Column('rationale',    sa.Text(),  nullable=False),
            sa.Column('alternatives', sa.JSON(),  nullable=True),
            sa.Column('inputs',       sa.JSON(),  nullable=True),
            sa.Column('outputs',      sa.JSON(),  nullable=True),
            # ── Outcome ───────────────────────────────────────────────────────
            sa.Column('outcome',      sa.String(16), nullable=False, server_default='pending'),
            sa.Column('error',        sa.Text(),     nullable=True),
            sa.Column('tokens_used',  sa.Integer(),  nullable=False, server_default='0'),
            sa.Column('duration_ms',  sa.Float(),    nullable=False, server_default='0.0'),
            sa.Column('started_at',   sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_reasoning_steps_step_id',           'reasoning_steps', ['step_id'],              unique=True)
        op.create_index('ix_reasoning_steps_trace_id',          'reasoning_steps', ['trace_id'])
        op.create_index('ix_reasoning_steps_phase',             'reasoning_steps', ['phase'])
        op.create_index('ix_reasoning_steps_outcome',           'reasoning_steps', ['outcome'])
        op.create_index('ix_reasoning_steps_trace_id_sequence', 'reasoning_steps', ['trace_id', 'sequence'])
        print("  ✅ Created reasoning_steps table")
    else:
        print("  ℹ️  reasoning_steps already exists")

    task_columns = {col['name'] for col in inspector.get_columns('tasks')}
    if 'latest_trace_id' not in task_columns:
        op.add_column('tasks', sa.Column('latest_trace_id', sa.String(64), nullable=True))
        print("  ✅ Added tasks.latest_trace_id")
    else:
        print("  ℹ️  tasks.latest_trace_id already exists")

    try:
        row = conn.execute(text(
            "SELECT config_value FROM db_maintenance_config "
            "WHERE config_key = 'analyze_tables'"
        )).fetchone()
        if row:
            current = json.loads(row[0])
            added = []
            for tbl in ('reasoning_traces', 'reasoning_steps'):
                if tbl not in current:
                    current.append(tbl)
                    added.append(tbl)
            if added:
                conn.execute(text(
                    "UPDATE db_maintenance_config "
                    "SET config_value = :val, updated_at = NOW() "
                    "WHERE config_key = 'analyze_tables'"
                ), {"val": json.dumps(current)})
                print(f"  ✅ Extended db_maintenance_config ANALYZE list: added {added}")
            else:
                print("  ℹ️  db_maintenance_config ANALYZE list already up to date")
        else:
            print("  ℹ️  db_maintenance_config row not found — skipping ANALYZE update")
    except Exception as exc:
        print(f"  ℹ️  Could not update db_maintenance_config: {exc}")

    # =========================================================================
    # 004 — Chat performance indexes
    # =========================================================================
    print("\n--- 004: Chat Indexes ---")

    # Re-inspect after table creation above
    inspector = Inspector.from_engine(conn)

    if not _index_exists(inspector, 'chat_messages', 'idx_chat_messages_user_created'):
        op.create_index(
            'idx_chat_messages_user_created',
            'chat_messages',
            ['user_id', sa.text('created_at DESC')],
            unique=False,
            postgresql_using='btree',
        )
        print("  ✅ Created idx_chat_messages_user_created")
    else:
        print("  ℹ️  idx_chat_messages_user_created already exists")

    if not _index_exists(inspector, 'chat_messages', 'idx_chat_messages_conversation'):
        op.create_index(
            'idx_chat_messages_conversation',
            'chat_messages',
            ['conversation_id', sa.text('created_at DESC')],
            unique=False,
            postgresql_using='btree',
        )
        print("  ✅ Created idx_chat_messages_conversation")
    else:
        print("  ℹ️  idx_chat_messages_conversation already exists")

    if not _index_exists(inspector, 'conversations', 'idx_conversations_user_last_msg'):
        op.create_index(
            'idx_conversations_user_last_msg',
            'conversations',
            ['user_id', sa.text('last_message_at DESC')],
            unique=False,
            postgresql_using='btree',
        )
        print("  ✅ Created idx_conversations_user_last_msg")
    else:
        print("  ℹ️  idx_conversations_user_last_msg already exists")

    if not _index_exists(inspector, 'conversations', 'idx_conversations_user_active'):
        op.create_index(
            'idx_conversations_user_active',
            'conversations',
            ['user_id', 'is_deleted', 'is_archived'],
            unique=False,
            postgresql_using='btree',
        )
        print("  ✅ Created idx_conversations_user_active")
    else:
        print("  ℹ️  idx_conversations_user_active already exists")

    # =========================================================================
    # 005 — Phase 11 Ecosystem Expansion
    # =========================================================================
    print("\n--- 005: Phase 11 Ecosystem ---")

    # Re-inspect
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    # RBAC columns on users
    user_columns = {col['name'] for col in inspector.get_columns('users')}

    if 'role' not in user_columns:
        op.add_column('users', sa.Column('role', sa.String(30), nullable=False, server_default='observer'))
        print("  ✅ Added users.role")
    else:
        print("  ℹ️  users.role already exists")

    if 'delegated_by_id' not in user_columns:
        op.add_column('users', sa.Column('delegated_by_id', sa.String(36), nullable=True))
        op.create_foreign_key('fk_users_delegated_by_id', 'users', 'users', ['delegated_by_id'], ['id'])
        print("  ✅ Added users.delegated_by_id")
    else:
        print("  ℹ️  users.delegated_by_id already exists")

    if 'role_expires_at' not in user_columns:
        op.add_column('users', sa.Column('role_expires_at', sa.DateTime(timezone=True), nullable=True))
        print("  ✅ Added users.role_expires_at")
    else:
        print("  ℹ️  users.role_expires_at already exists")

    if 'delegations' not in existing_tables:
        op.create_table(
            'delegations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('grantor_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('grantee_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('capabilities', sa.JSON(), nullable=False),
            sa.Column('reason', sa.String(500), nullable=True),
            sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_emergency', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_delegations_grantor_id', 'delegations', ['grantor_id'])
        op.create_index('ix_delegations_grantee_id', 'delegations', ['grantee_id'])
        print("  ✅ Created delegations table")
    else:
        print("  ℹ️  delegations already exists")

    if 'federated_instances' not in existing_tables:
        op.create_table(
            'federated_instances',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('base_url', sa.String(255), nullable=False, unique=True),
            sa.Column('shared_secret_hash', sa.String(255), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('trust_level', sa.String(20), nullable=False, server_default='limited'),
            sa.Column('capabilities_shared', sa.JSON(), nullable=True),
            sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
            # signing_key included here (from 008) to avoid a separate ALTER TABLE
            sa.Column('signing_key', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created federated_instances table (incl. signing_key)")
    else:
        print("  ℹ️  federated_instances already exists")

    if 'federated_tasks' not in existing_tables:
        op.create_table(
            'federated_tasks',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('source_instance_id', sa.String(36), sa.ForeignKey('federated_instances.id'), nullable=True),
            sa.Column('target_instance_id', sa.String(36), sa.ForeignKey('federated_instances.id'), nullable=True),
            sa.Column('original_task_id', sa.String(36), nullable=False),
            sa.Column('local_task_id', sa.String(36), sa.ForeignKey('tasks.id'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('delegated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created federated_tasks table")
    else:
        print("  ℹ️  federated_tasks already exists")

    if 'federated_votes' not in existing_tables:
        op.create_table(
            'federated_votes',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('proposal_id', sa.String(36), nullable=False),
            sa.Column('participating_instances', sa.JSON(), nullable=True),
            sa.Column('votes', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='open'),
            sa.Column('closes_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created federated_votes table")
    else:
        print("  ℹ️  federated_votes already exists")

    if 'plugins' not in existing_tables:
        op.create_table(
            'plugins',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('author', sa.String(100), nullable=False),
            sa.Column('version', sa.String(20), nullable=False),
            sa.Column('plugin_type', sa.String(50), nullable=False),
            sa.Column('source_url', sa.String(255), nullable=True),
            sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('verification_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('install_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('rating', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('revenue_share_percent', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('config_schema', sa.JSON(), nullable=True),
            sa.Column('entry_point', sa.String(255), nullable=False),
            sa.Column('dependencies', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
            sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created plugins table")
    else:
        print("  ℹ️  plugins already exists")

    if 'plugin_installations' not in existing_tables:
        op.create_table(
            'plugin_installations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('plugin_id', sa.String(36), sa.ForeignKey('plugins.id', ondelete='CASCADE'), nullable=False),
            sa.Column('instance_id', sa.String(100), nullable=False, server_default='local'),
            sa.Column('config', sa.JSON(), nullable=True),
            sa.Column('installed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created plugin_installations table")
    else:
        print("  ℹ️  plugin_installations already exists")

    if 'plugin_reviews' not in existing_tables:
        op.create_table(
            'plugin_reviews',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('plugin_id', sa.String(36), sa.ForeignKey('plugins.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('rating', sa.Integer(), nullable=False),
            sa.Column('review_text', sa.String(1000), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created plugin_reviews table")
    else:
        print("  ℹ️  plugin_reviews already exists")

    if 'device_tokens' not in existing_tables:
        op.create_table(
            'device_tokens',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('platform', sa.String(20), nullable=False),
            sa.Column('token', sa.String(255), nullable=False, unique=True),
            sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
            # is_active included here (from 006) to avoid a separate ALTER TABLE
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("  ✅ Created device_tokens table (incl. is_active)")
    else:
        print("  ℹ️  device_tokens already exists")

    # =========================================================================
    # 006 — notification_preferences + device_tokens.is_active backfill
    # =========================================================================
    print("\n--- 006: Notification Preferences ---")

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'notification_preferences' not in existing_tables:
        op.create_table(
            'notification_preferences',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'),
                      nullable=False, unique=True),
            sa.Column('votes_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('alerts_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('tasks_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('constitutional_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('quiet_hours_start', sa.String(5), nullable=True),
            sa.Column('quiet_hours_end', sa.String(5), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'])
        print("  ✅ Created notification_preferences table")
    else:
        print("  ℹ️  notification_preferences already exists")

    # Backfill device_tokens.is_active if the table pre-existed without it
    if 'device_tokens' in existing_tables:
        dt_columns = {col['name'] for col in inspector.get_columns('device_tokens')}
        if 'is_active' not in dt_columns:
            op.add_column('device_tokens',
                          sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
            print("  ✅ Added device_tokens.is_active (backfill)")
        else:
            print("  ℹ️  device_tokens.is_active already exists")

    # =========================================================================
    # 007 — audit_logs.screenshot_url + critique_reviews.learning_extracted
    # =========================================================================
    print("\n--- 007: Audit Screenshot URL ---")

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    audit_cols = {col['name'] for col in inspector.get_columns('audit_logs')}
    if 'screenshot_url' not in audit_cols:
        op.add_column('audit_logs',
                      sa.Column('screenshot_url', sa.String(500), nullable=True))
        print("  ✅ Added audit_logs.screenshot_url")
    else:
        print("  ℹ️  audit_logs.screenshot_url already exists")

    if 'critique_reviews' in existing_tables:
        critique_cols = {col['name'] for col in inspector.get_columns('critique_reviews')}
        if 'learning_extracted' not in critique_cols:
            op.add_column('critique_reviews',
                          sa.Column('learning_extracted', sa.Boolean(),
                                    nullable=False, server_default='false'))
            print("  ✅ Added critique_reviews.learning_extracted")
        else:
            print("  ℹ️  critique_reviews.learning_extracted already exists")
    else:
        print("  ⚠️  critique_reviews table not found — skipping")

    # =========================================================================
    # 008 — Federation HMAC: signing_key + status check
    # =========================================================================
    print("\n--- 008: Federation HMAC ---")

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'federated_instances' in existing_tables:
        existing_cols = {col['name'] for col in inspector.get_columns('federated_instances')}
        if 'signing_key' not in existing_cols:
            op.add_column('federated_instances',
                          sa.Column('signing_key', sa.String(255), nullable=True))
            op.execute(
                "UPDATE federated_instances "
                "SET signing_key = shared_secret_hash "
                "WHERE signing_key IS NULL"
            )
            print("  ✅ Added federated_instances.signing_key and back-filled from shared_secret_hash")
            print("  ⚠️  Re-register peers to enable proper HMAC signing")
        else:
            print("  ℹ️  federated_instances.signing_key already exists")

        if 'federated_tasks' in existing_tables:
            status_col = next(
                (col for col in inspector.get_columns('federated_tasks') if col['name'] == 'status'),
                None,
            )
            if status_col:
                col_type = str(status_col['type']).upper()
                if 'CHAR' in col_type or 'TEXT' in col_type:
                    print("  ✅ federated_tasks.status is VARCHAR — 'delivered' value accepted")
                else:
                    print(f"  ⚠️  federated_tasks.status type is '{col_type}' — verify 'delivered' is accepted")
    else:
        print("  ℹ️  federated_instances not found — skipped (federation not enabled?)")

    # =========================================================================
    # 009 — A/B Testing tables + indexes + schema hardening
    # =========================================================================
    print("\n--- 009: A/B Testing ---")

    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    # experiments
    if 'experiments' not in existing_tables:
        op.create_table(
            'experiments',
            sa.Column('id',           sa.String(36),  primary_key=True),
            sa.Column('name',         sa.String(200), nullable=False),
            sa.Column('description',  sa.Text(),      nullable=True),
            sa.Column('task_template',   sa.Text(),    nullable=False),
            sa.Column('system_prompt',   sa.Text(),    nullable=True),
            sa.Column('test_iterations', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_by',   sa.String(100), nullable=False, server_default='unknown'),
            sa.Column('status',       sa.String(20),  nullable=False, server_default='draft'),
            sa.Column('created_at',   sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('started_at',   sa.DateTime(),  nullable=True),
            sa.Column('completed_at', sa.DateTime(),  nullable=True),
        )
        print("  ✅ Created experiments table")
    else:
        print("  ℹ️  experiments already exists — applying schema hardening")
        exp_cols = {col['name'] for col in inspector.get_columns('experiments')}
        if 'created_by' in exp_cols:
            conn.execute(sa.text(
                "UPDATE experiments SET created_by = 'unknown' WHERE created_by IS NULL"
            ))
            op.alter_column('experiments', 'created_by',
                            nullable=False, server_default='unknown')
            print("  ✅ Hardened experiments.created_by (NOT NULL)")
        else:
            op.add_column('experiments',
                          sa.Column('created_by', sa.String(100),
                                    nullable=False, server_default='unknown'))
            print("  ✅ Added experiments.created_by")

    inspector = Inspector.from_engine(conn)
    for idx_name, columns in [
        ('ix_experiments_status',            ['status']),
        ('ix_experiments_created_at',        ['created_at']),
        ('ix_experiments_created_by_status', ['created_by', 'status']),
    ]:
        if not _index_exists(inspector, 'experiments', idx_name):
            op.create_index(idx_name, 'experiments', columns)
            print(f"  ✅ Created index {idx_name}")
        else:
            print(f"  ℹ️  Index {idx_name} already exists")

    # experiment_runs
    if 'experiment_runs' not in existing_tables:
        op.create_table(
            'experiment_runs',
            sa.Column('id',            sa.String(36), primary_key=True),
            sa.Column('experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('config_id',        sa.String(36),  nullable=True),
            sa.Column('model_name',       sa.String(100), nullable=True),
            sa.Column('iteration_number', sa.Integer(),   nullable=False, server_default='1'),
            sa.Column('status',        sa.String(20),  nullable=False, server_default='pending'),
            sa.Column('started_at',    sa.DateTime(),  nullable=True),
            sa.Column('completed_at',  sa.DateTime(),  nullable=True),
            sa.Column('error_message', sa.Text(),      nullable=True),
            sa.Column('output_text',  sa.Text(),    nullable=True),
            sa.Column('tokens_used',  sa.Integer(), nullable=True),
            sa.Column('latency_ms',   sa.Integer(), nullable=True),
            sa.Column('cost_usd',     sa.Float(),   nullable=True),
            sa.Column('critic_plan_score',         sa.Float(),   nullable=True),
            sa.Column('critic_code_score',         sa.Float(),   nullable=True),
            sa.Column('critic_output_score',       sa.Float(),   nullable=True),
            sa.Column('overall_quality_score',     sa.Float(),   nullable=True),
            sa.Column('critic_feedback',           sa.JSON(),    nullable=True),
            sa.Column('constitutional_violations', sa.Integer(), nullable=False, server_default='0'),
        )
        print("  ✅ Created experiment_runs table")
    else:
        print("  ℹ️  experiment_runs already exists")

    inspector = Inspector.from_engine(conn)
    for idx_name, columns in [
        ('ix_runs_experiment_id',     ['experiment_id']),
        ('ix_runs_experiment_status', ['experiment_id', 'status']),
    ]:
        if not _index_exists(inspector, 'experiment_runs', idx_name):
            op.create_index(idx_name, 'experiment_runs', columns)
            print(f"  ✅ Created index {idx_name}")
        else:
            print(f"  ℹ️  Index {idx_name} already exists")

    # experiment_results
    if 'experiment_results' not in existing_tables:
        op.create_table(
            'experiment_results',
            sa.Column('id',            sa.String(36), primary_key=True),
            sa.Column('experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('winner_config_id',         sa.String(36),  nullable=True),
            sa.Column('winner_model_name',        sa.String(100), nullable=True),
            sa.Column('selection_reason',         sa.Text(),      nullable=True),
            sa.Column('model_comparisons',        sa.JSON(),      nullable=True),
            sa.Column('statistical_significance', sa.Float(),     nullable=True),
            sa.Column('recommended_for_similar',  sa.Boolean(),   nullable=False, server_default='false'),
            sa.Column('confidence_score',         sa.Float(),     nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        print("  ✅ Created experiment_results table")
    else:
        print("  ℹ️  experiment_results already exists")

    inspector = Inspector.from_engine(conn)
    if not _index_exists(inspector, 'experiment_results', 'ix_results_experiment_id'):
        op.create_index('ix_results_experiment_id', 'experiment_results', ['experiment_id'])
        print("  ✅ Created index ix_results_experiment_id")
    else:
        print("  ℹ️  Index ix_results_experiment_id already exists")

    # model_performance_cache
    if 'model_performance_cache' not in existing_tables:
        op.create_table(
            'model_performance_cache',
            sa.Column('id',              sa.String(36),  primary_key=True),
            sa.Column('task_category',   sa.String(50),  nullable=False),
            sa.Column('task_complexity', sa.String(20),  nullable=True),
            sa.Column('best_config_id',  sa.String(36),  nullable=True),
            sa.Column('best_model_name', sa.String(100), nullable=True),
            sa.Column('avg_latency_ms',    sa.Integer(), nullable=True),
            sa.Column('avg_cost_usd',      sa.Float(),   nullable=True),
            sa.Column('avg_quality_score', sa.Float(),   nullable=True),
            sa.Column('success_rate',      sa.Float(),   nullable=True),
            sa.Column('sample_size',       sa.Integer(), nullable=False, server_default='0'),
            sa.Column('derived_from_experiment_id', sa.String(36), nullable=True),
            sa.Column('last_updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        print("  ✅ Created model_performance_cache table")
    else:
        print("  ℹ️  model_performance_cache already exists — applying schema hardening")
        mpc_cols = {col['name'] for col in inspector.get_columns('model_performance_cache')}
        if 'last_updated' in mpc_cols:
            conn.execute(sa.text(
                "UPDATE model_performance_cache "
                "SET last_updated = NOW() WHERE last_updated IS NULL"
            ))
            op.alter_column('model_performance_cache', 'last_updated',
                            nullable=False, server_default=sa.func.now())
            print("  ✅ Hardened model_performance_cache.last_updated (NOT NULL)")

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
            'uq_perf_cache_task_category',
            'model_performance_cache',
            ['task_category'],
        )
        print("  ✅ Created unique constraint uq_perf_cache_task_category")
    else:
        print("  ℹ️  uq_perf_cache_task_category already exists")

    if not _index_exists(inspector, 'model_performance_cache', 'ix_perf_cache_last_updated'):
        op.create_index('ix_perf_cache_last_updated', 'model_performance_cache', ['last_updated'])
        print("  ✅ Created index ix_perf_cache_last_updated")
    else:
        print("  ℹ️  Index ix_perf_cache_last_updated already exists")

    print("\n" + "=" * 70)
    print("✅ Combined migration 003_migration (003–009) completed successfully!")
    print("=" * 70)
    print("Summary of changes:")
    print("  003  reasoning_traces, reasoning_steps, tasks.latest_trace_id")
    print("  004  Chat indexes (chat_messages, conversations)")
    print("  005  RBAC on users, delegations, federated_*, plugins, device_tokens")
    print("  006  notification_preferences, device_tokens.is_active")
    print("  007  audit_logs.screenshot_url, critique_reviews.learning_extracted")
    print("  008  federated_instances.signing_key (HMAC)")
    print("  009  experiments, experiment_runs, experiment_results,")
    print("       model_performance_cache + indexes + schema hardening")
    print("=" * 70)


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🔄 Starting downgrade of combined migration 003_migration (003–009)...")

    # ── 009 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 009: A/B Testing ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'model_performance_cache' in existing_tables:
        if _index_exists(inspector, 'model_performance_cache', 'ix_perf_cache_last_updated'):
            op.drop_index('ix_perf_cache_last_updated', table_name='model_performance_cache')
        if _constraint_exists(inspector, 'model_performance_cache', 'uq_perf_cache_task_category'):
            op.drop_constraint('uq_perf_cache_task_category', 'model_performance_cache', type_='unique')
        op.drop_table('model_performance_cache')
        print("  ✅ Dropped model_performance_cache")

    if 'experiment_results' in existing_tables:
        if _index_exists(inspector, 'experiment_results', 'ix_results_experiment_id'):
            op.drop_index('ix_results_experiment_id', table_name='experiment_results')
        op.drop_table('experiment_results')
        print("  ✅ Dropped experiment_results")

    if 'experiment_runs' in existing_tables:
        for idx in ('ix_runs_experiment_status', 'ix_runs_experiment_id'):
            if _index_exists(inspector, 'experiment_runs', idx):
                op.drop_index(idx, table_name='experiment_runs')
        op.drop_table('experiment_runs')
        print("  ✅ Dropped experiment_runs")

    if 'experiments' in existing_tables:
        for idx in ('ix_experiments_created_by_status', 'ix_experiments_created_at', 'ix_experiments_status'):
            if _index_exists(inspector, 'experiments', idx):
                op.drop_index(idx, table_name='experiments')
        op.drop_table('experiments')
        print("  ✅ Dropped experiments")

    # ── 008 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 008: Federation HMAC ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'federated_instances' in existing_tables:
        existing_cols = {col['name'] for col in inspector.get_columns('federated_instances')}
        if 'signing_key' in existing_cols:
            op.drop_column('federated_instances', 'signing_key')
            print("  ✅ Dropped federated_instances.signing_key")

    # ── 007 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 007: Audit Screenshot URL ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'critique_reviews' in existing_tables:
        critique_cols = {col['name'] for col in inspector.get_columns('critique_reviews')}
        if 'learning_extracted' in critique_cols:
            op.drop_column('critique_reviews', 'learning_extracted')
            print("  ✅ Dropped critique_reviews.learning_extracted")

    audit_cols = {col['name'] for col in inspector.get_columns('audit_logs')}
    if 'screenshot_url' in audit_cols:
        op.drop_column('audit_logs', 'screenshot_url')
        print("  ✅ Dropped audit_logs.screenshot_url")

    # ── 006 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 006: Notification Preferences ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    if 'notification_preferences' in existing_tables:
        op.drop_table('notification_preferences')
        print("  ✅ Dropped notification_preferences")

    # ── 005 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 005: Phase 11 Ecosystem ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    for tbl in ('device_tokens', 'plugin_reviews', 'plugin_installations', 'plugins',
                'federated_votes', 'federated_tasks', 'federated_instances', 'delegations'):
        if tbl in existing_tables:
            op.drop_table(tbl)
            print(f"  ✅ Dropped {tbl}")

    user_columns = {col['name'] for col in inspector.get_columns('users')}
    if 'role_expires_at' in user_columns:
        op.drop_column('users', 'role_expires_at')
    if 'delegated_by_id' in user_columns:
        op.drop_constraint('fk_users_delegated_by_id', 'users', type_='foreignkey')
        op.drop_column('users', 'delegated_by_id')
    if 'role' in user_columns:
        op.drop_column('users', 'role')
    print("  ✅ Reverted users RBAC columns")

    # ── 004 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 004: Chat Indexes ---")
    inspector = Inspector.from_engine(conn)

    for idx, tbl in [
        ('idx_conversations_user_active',   'conversations'),
        ('idx_conversations_user_last_msg', 'conversations'),
        ('idx_chat_messages_conversation',  'chat_messages'),
        ('idx_chat_messages_user_created',  'chat_messages'),
    ]:
        if _index_exists(inspector, tbl, idx):
            op.drop_index(idx, table_name=tbl)
            print(f"  ✅ Dropped {idx}")

    # ── 003 ──────────────────────────────────────────────────────────────────
    print("\n--- Reverting 003: Reasoning Traces ---")
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    task_columns = {col['name'] for col in inspector.get_columns('tasks')}
    if 'latest_trace_id' in task_columns:
        op.drop_column('tasks', 'latest_trace_id')
        print("  ✅ Dropped tasks.latest_trace_id")

    if 'reasoning_steps' in existing_tables:
        for idx in ('ix_reasoning_steps_trace_id_sequence', 'ix_reasoning_steps_outcome',
                    'ix_reasoning_steps_phase', 'ix_reasoning_steps_trace_id',
                    'ix_reasoning_steps_step_id'):
            try:
                op.drop_index(idx, table_name='reasoning_steps')
            except Exception:
                pass
        op.drop_table('reasoning_steps')
        print("  ✅ Dropped reasoning_steps")

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
        print("  ✅ Dropped reasoning_traces")

    try:
        row = conn.execute(text(
            "SELECT config_value FROM db_maintenance_config "
            "WHERE config_key = 'analyze_tables'"
        )).fetchone()
        if row:
            current = json.loads(row[0])
            restored = [t for t in current if t not in ('reasoning_traces', 'reasoning_steps')]
            conn.execute(text(
                "UPDATE db_maintenance_config "
                "SET config_value = :val, updated_at = NOW() "
                "WHERE config_key = 'analyze_tables'"
            ), {"val": json.dumps(restored)})
            print("  ✅ Restored db_maintenance_config ANALYZE list")
    except Exception as exc:
        print(f"  ℹ️  Could not restore db_maintenance_config: {exc}")

    print("\n✅ Downgrade of combined migration 003_migration (003–009) completed")