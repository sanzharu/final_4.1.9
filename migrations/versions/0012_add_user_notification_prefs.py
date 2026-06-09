"""Add notify_comments and notify_followers to users

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('users')}

    if 'notify_comments' not in cols:
        op.add_column('users', sa.Column('notify_comments', sa.Boolean(), nullable=False, server_default='true'))
        print("  OK: added notify_comments")
    else:
        print("  SKIP: notify_comments already exists")

    if 'notify_followers' not in cols:
        op.add_column('users', sa.Column('notify_followers', sa.Boolean(), nullable=False, server_default='true'))
        print("  OK: added notify_followers")
    else:
        print("  SKIP: notify_followers already exists")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('users')}
    if 'notify_comments' in cols:
        op.drop_column('users', 'notify_comments')
    if 'notify_followers' in cols:
        op.drop_column('users', 'notify_followers')
