"""
A/B Testing — tables, indexes, and schema hardening

Revision ID: 009_ab_testing_indexes
Revises: 008_federation_hmac
Create Date: 2026-03-06

What this migration does
─────────────────────────
1.  Creates the four A/B testing tables if they do not already exist:
      experiments, experiment_runs, experiment_results,
      model_performance_cache
    (They may already be present on databases that were bootstrapped via
    SQLAlchemy's create_all() rather than via Alembic exclusively.)

2.  Adds performance indexes on every table that was missing them:
      experiments            → (status), (created_at), (created_by, status)
      experiment_runs        → (experiment_id), (experiment_id, status)
      experiment_results     → (experiment_id)
      model_performance_cache→ (last_updated)

3.  Schema correctness fixes:
      experiments.created_by          — backfill NULLs → 'unknown', set NOT NULL
      model_performance_cache         — unique constraint on task_category
                                        (safe upsert in service layer)
      model_performance_cache.last_updated — backfill NULLs → NOW(), set NOT NULL
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '009_ab_testing_indexes'
down_revision = '008_federation_hmac'
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

    print("🚀 Starting migration 009_ab_testing_indexes...")

    # =========================================================================
    # 1.  experiments
    # =========================================================================
    if 'experiments' not in existing_tables:
        op.create_table(
            'experiments',
            sa.Column('id',           sa.String(36),  primary_key=True),
            sa.Column('name',         sa.String(200), nullable=False),
            sa.Column('description',  sa.Text(),      nullable=True),
            # Test configuration
            sa.Column('task_template',   sa.Text(),    nullable=False),
            sa.Column('system_prompt',   sa.Text(),    nullable=True),
            sa.Column('test_iterations', sa.Integer(), nullable=False, server_default='1'),
            # Ownership & status
            sa.Column('created_by',   sa.String(100), nullable=False, server_default='unknown'),
            sa.Column('status',       sa.String(20),  nullable=False, server_default='draft'),
            sa.Column('created_at',   sa.DateTime(),  nullable=False, server_default=sa.func.now()),
            sa.Column('started_at',   sa.DateTime(),  nullable=True),
            sa.Column('completed_at', sa.DateTime(),  nullable=True),
        )
        print("  ✅ Created experiments table")
    else:
        print("  ℹ️  experiments already exists — skipping table creation")

        # Schema fix: created_by must not be NULL
        exp_cols = {col['name'] for col in inspector.get_columns('experiments')}
        if 'created_by' in exp_cols:
            conn.execute(sa.text(
                "UPDATE experiments SET created_by = 'unknown' WHERE created_by IS NULL"
            ))
            op.alter_column(
                'experiments', 'created_by',
                nullable=False,
                server_default='unknown',
            )
            print("  ✅ Hardened experiments.created_by (NOT NULL, default='unknown')")
        else:
            op.add_column(
                'experiments',
                sa.Column('created_by', sa.String(100), nullable=False, server_default='unknown'),
            )
            print("  ✅ Added experiments.created_by")

    # Indexes on experiments
    for idx_name, columns in [
        ('ix_experiments_status',              ['status']),
        ('ix_experiments_created_at',          ['created_at']),
        ('ix_experiments_created_by_status',   ['created_by', 'status']),
    ]:
        if not _index_exists(inspector, 'experiments', idx_name):
            op.create_index(idx_name, 'experiments', columns)
            print(f"  ✅ Created index {idx_name}")
        else:
            print(f"  ℹ️  Index {idx_name} already exists — skipping")

    # =========================================================================
    # 2.  experiment_runs
    # =========================================================================
    if 'experiment_runs' not in existing_tables:
        op.create_table(
            'experiment_runs',
            sa.Column('id',            sa.String(36), primary_key=True),
            sa.Column('experiment_id', sa.String(36),
                      sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False),
            # Model configuration
            sa.Column('config_id',        sa.String(36), nullable=True),
            sa.Column('model_name',       sa.String(100), nullable=True),
            sa.Column('iteration_number', sa.Integer(),   nullable=False, server_default='1'),
            # Lifecycle
            sa.Column('status',        sa.String(20),  nullable=False, server_default='pending'),
            sa.Column('started_at',    sa.DateTime(),  nullable=True),
            sa.Column('completed_at',  sa.DateTime(),  nullable=True),
            sa.Column('error_message', sa.Text(),      nullable=True),
            # Raw output
            sa.Column('output_text',  sa.Text(),    nullable=True),
            sa.Column('tokens_used',  sa.Integer(), nullable=True),
            sa.Column('latency_ms',   sa.Integer(), nullable=True),
            sa.Column('cost_usd',     sa.Float(),   nullable=True),
            # Quality metrics
            sa.Column('critic_plan_score',         sa.Float(),   nullable=True),
            sa.Column('critic_code_score',         sa.Float(),   nullable=True),
            sa.Column('critic_output_score',       sa.Float(),   nullable=True),
            sa.Column('overall_quality_score',     sa.Float(),   nullable=True),
            sa.Column('critic_feedback',           sa.JSON(),    nullable=True),
            sa.Column('constitutional_violations', sa.Integer(), nullable=False, server_default='0'),
        )
        print("  ✅ Created experiment_runs table")
    else:
        print("  ℹ️  experiment_runs already exists — skipping table creation")

    for idx_name, columns in [
        ('ix_runs_experiment_id',     ['experiment_id']),
        ('ix_runs_experiment_status', ['experiment_id', 'status']),
    ]:
        if not _index_exists(inspector, 'experiment_runs', idx_name):
            op.create_index(idx_name, 'experiment_runs', columns)
            print(f"  ✅ Created index {idx_name}")
        else:
            print(f"  ℹ️  Index {idx_name} already exists — skipping")

    # =========================================================================
    # 3.  experiment_results
    # =========================================================================
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
        print("  ℹ️  experiment_results already exists — skipping table creation")

    if not _index_exists(inspector, 'experiment_results', 'ix_results_experiment_id'):
        op.create_index('ix_results_experiment_id', 'experiment_results', ['experiment_id'])
        print("  ✅ Created index ix_results_experiment_id")
    else:
        print("  ℹ️  Index ix_results_experiment_id already exists — skipping")

    # =========================================================================
    # 4.  model_performance_cache
    # =========================================================================
    if 'model_performance_cache' not in existing_tables:
        op.create_table(
            'model_performance_cache',
            sa.Column('id',              sa.String(36), primary_key=True),
            sa.Column('task_category',   sa.String(50), nullable=False),
            sa.Column('task_complexity', sa.String(20), nullable=True),
            sa.Column('best_config_id',  sa.String(36), nullable=True),
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
        print("  ℹ️  model_performance_cache already exists — skipping table creation")

        # Schema fix: last_updated must not be NULL
        mpc_cols = {col['name'] for col in inspector.get_columns('model_performance_cache')}
        if 'last_updated' in mpc_cols:
            conn.execute(sa.text(
                "UPDATE model_performance_cache "
                "SET last_updated = NOW() WHERE last_updated IS NULL"
            ))
            op.alter_column(
                'model_performance_cache', 'last_updated',
                nullable=False,
                server_default=sa.func.now(),
            )
            print("  ✅ Hardened model_performance_cache.last_updated (NOT NULL)")

    # Unique constraint: one recommendation row per task_category
    if not _constraint_exists(inspector, 'model_performance_cache', 'uq_perf_cache_task_category'):
        # Remove duplicate rows first (keep the most recently updated one per category)
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
        print("  ℹ️  Unique constraint uq_perf_cache_task_category already exists — skipping")

    if not _index_exists(inspector, 'model_performance_cache', 'ix_perf_cache_last_updated'):
        op.create_index('ix_perf_cache_last_updated', 'model_performance_cache', ['last_updated'])
        print("  ✅ Created index ix_perf_cache_last_updated")
    else:
        print("  ℹ️  Index ix_perf_cache_last_updated already exists — skipping")

    print("\n" + "=" * 70)
    print("✅ Migration 009_ab_testing_indexes completed successfully!")
    print("=" * 70)
    print("Changes applied:")
    print("  • experiments              — created if absent; created_by NOT NULL; 3 indexes")
    print("  • experiment_runs          — created if absent; 2 indexes")
    print("  • experiment_results       — created if absent; 1 index")
    print("  • model_performance_cache  — created if absent; unique(task_category); 1 index")
    print("=" * 70)


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🔄 Starting downgrade of 009_ab_testing_indexes...")

    # ── model_performance_cache ───────────────────────────────────────────────
    if 'model_performance_cache' in existing_tables:
        if _index_exists(inspector, 'model_performance_cache', 'ix_perf_cache_last_updated'):
            op.drop_index('ix_perf_cache_last_updated', table_name='model_performance_cache')
            print("  ✅ Dropped index ix_perf_cache_last_updated")
        if _constraint_exists(inspector, 'model_performance_cache', 'uq_perf_cache_task_category'):
            op.drop_constraint(
                'uq_perf_cache_task_category',
                'model_performance_cache',
                type_='unique',
            )
            print("  ✅ Dropped constraint uq_perf_cache_task_category")

    # ── experiment_results ────────────────────────────────────────────────────
    if 'experiment_results' in existing_tables:
        if _index_exists(inspector, 'experiment_results', 'ix_results_experiment_id'):
            op.drop_index('ix_results_experiment_id', table_name='experiment_results')
            print("  ✅ Dropped index ix_results_experiment_id")

    # ── experiment_runs ───────────────────────────────────────────────────────
    if 'experiment_runs' in existing_tables:
        for idx in ('ix_runs_experiment_status', 'ix_runs_experiment_id'):
            if _index_exists(inspector, 'experiment_runs', idx):
                op.drop_index(idx, table_name='experiment_runs')
                print(f"  ✅ Dropped index {idx}")

    # ── experiments ───────────────────────────────────────────────────────────
    if 'experiments' in existing_tables:
        for idx in (
            'ix_experiments_created_by_status',
            'ix_experiments_created_at',
            'ix_experiments_status',
        ):
            if _index_exists(inspector, 'experiments', idx):
                op.drop_index(idx, table_name='experiments')
                print(f"  ✅ Dropped index {idx}")

    print("✅ Downgrade 009_ab_testing_indexes completed")