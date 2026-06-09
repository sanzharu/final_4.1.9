"""Add reading_status column to bookmarks table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11 00:00:00.000000

Adds reading_status field: 'reading' | 'will_read' | 'read' | 'dropped'
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('bookmarks')]
    if 'reading_status' not in cols:
        op.add_column(
            'bookmarks',
            sa.Column('reading_status', sa.String(30), nullable=True, server_default='reading')
        )
        print("  OK: added reading_status to bookmarks")
    else:
        print("  SKIP: reading_status already exists")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('bookmarks')]
    if 'reading_status' in cols:
        op.drop_column('bookmarks', 'reading_status')
