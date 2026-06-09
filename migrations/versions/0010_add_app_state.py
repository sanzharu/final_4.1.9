"""Add app_state table for one-time seed tracking

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29 00:00:00.000000

Creates a simple key-value store used by the application to record
one-time operations (like initial data seeding) so they are never
re-executed on container restart.
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    if 'app_state' in existing_tables:
        print("  SKIP: app_state table already exists")
        return

    op.create_table(
        'app_state',
        sa.Column('key',        sa.Text(),                       nullable=False,  primary_key=True),
        sa.Column('value',      sa.Text(),                       nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'),               nullable=False),
    )
    print("  OK: created app_state table")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'app_state' in insp.get_table_names():
        op.drop_table('app_state')
        print("  OK: dropped app_state table")
