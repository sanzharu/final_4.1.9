"""Initial schema — create all tables

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Import all models so they register with Base.metadata,
    # then create any tables that don't exist yet (checkfirst=True
    # makes it safe to run against an existing database).
    from app.db.base import Base
    import app.models.user        # noqa: F401
    import app.models.book        # noqa: F401
    import app.models.chapter     # noqa: F401
    import app.models.social      # noqa: F401
    import app.models.interaction # noqa: F401
    import app.models.tag         # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    from app.db.base import Base
    import app.models.user        # noqa: F401
    import app.models.book        # noqa: F401
    import app.models.chapter     # noqa: F401
    import app.models.social      # noqa: F401
    import app.models.interaction # noqa: F401
    import app.models.tag         # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
