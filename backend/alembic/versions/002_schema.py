"""002_schema

Revision ID: 002_schema
Revises: 001_schema
Create Date: 2025-02-22 00:00:00.000000

Fix: config column is typed as JSON (not JSONB), so we cast it to jsonb for
     the jsonb_set() call, then cast the result back to json for storage.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_schema'
down_revision = '001_schema'
branch_labels = None
depends_on = None


def upgrade():
    # Update existing WhatsApp channels to use cloud_api by default.
    #
    # The config column is stored as JSON (not JSONB), so we must:
    #   1. Cast config to jsonb so jsonb_set() accepts it.
    #   2. Cast the result back to json so it can be written to the column.
    #
    # COALESCE must also work in jsonb-land, so we cast the fallback literal
    # to jsonb explicitly — and the whole COALESCE expression returns jsonb.
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
          AND (
              config IS NULL
              OR config->>'provider' IS NULL
          )
    """)

    # Document the provider field in a column comment.
    # NOTE: COMMENT ON COLUMN requires the table + column to exist; it is safe
    #       to run even when config already has a comment.
    op.execute("""
        COMMENT ON COLUMN external_channels.config IS
        'Channel configuration JSON. For WhatsApp: includes provider (cloud_api|web_bridge), credentials, and connection settings'
    """)


def downgrade():
    # Remove the provider field from WhatsApp channel configs.
    # config is JSON, so cast to jsonb for the - operator, then back to json.
    op.execute("""
        UPDATE external_channels
        SET config = (config::jsonb - 'provider')::json
        WHERE channel_type = 'whatsapp'
    """)