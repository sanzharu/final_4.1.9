"""Fix book_tags.is_spoiler column type from INTEGER to BOOLEAN

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-08

The SQLAlchemy model declares is_spoiler as Boolean but the DB column
was created as INTEGER, causing asyncpg DatatypeMismatchError on insert.
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name']: c for c in insp.get_columns('book_tags')}
    col = cols.get('is_spoiler')
    if col is None:
        print("  SKIP: is_spoiler column not found")
        return
    col_type = str(col['type']).upper()
    if 'BOOL' in col_type:
        print("  SKIP: is_spoiler already BOOLEAN")
        return
    op.execute(
        "ALTER TABLE book_tags ALTER COLUMN is_spoiler TYPE BOOLEAN "
        "USING (is_spoiler != 0)"
    )
    print("  OK: converted is_spoiler from INTEGER to BOOLEAN")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE book_tags ALTER COLUMN is_spoiler TYPE INTEGER "
        "USING is_spoiler::integer"
    )
    print("  OK: reverted is_spoiler from BOOLEAN to INTEGER")
