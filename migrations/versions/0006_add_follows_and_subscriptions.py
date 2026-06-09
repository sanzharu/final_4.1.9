"""Add follows and book_subscriptions tables

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    # Таблицы уже созданы миграцией 0001 через Base.metadata.create_all().
    # Используем IF NOT EXISTS чтобы миграция была идемпотентной.
    op.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id SERIAL PRIMARY KEY,
            follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT uq_follow UNIQUE (follower_id, following_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_follows_id ON follows (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_follows_follower_id ON follows (follower_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_follows_following_id ON follows (following_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS book_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT uq_book_sub UNIQUE (user_id, book_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_book_subscriptions_id ON book_subscriptions (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_book_subscriptions_user_id ON book_subscriptions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_book_subscriptions_book_id ON book_subscriptions (book_id)")


def downgrade():
    op.drop_table('book_subscriptions')
    op.drop_table('follows')
