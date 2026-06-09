-- Emergency fix: add all missing columns
-- Run this directly: psql -d your_db_name -f fix_db.sql

-- books table
ALTER TABLE books ADD COLUMN IF NOT EXISTS direction VARCHAR(20) DEFAULT 'gen';
ALTER TABLE books ADD COLUMN IF NOT EXISTS is_draft_hidden BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE books ADD COLUMN IF NOT EXISTS is_on_moderation BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE books ADD COLUMN IF NOT EXISTS content_warnings VARCHAR(500);

-- chapters table
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS is_draft_hidden BOOLEAN NOT NULL DEFAULT false;

-- users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS followers_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS works_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE;

-- reports table
CREATE TABLE IF NOT EXISTS reports (
    id           SERIAL PRIMARY KEY,
    reporter_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id      INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    reason       VARCHAR(100) NOT NULL,
    comment      VARCHAR(500),
    is_resolved  BOOLEAN NOT NULL DEFAULT false,
    resolved_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        VARCHAR(50) NOT NULL,
    title       VARCHAR(200) NOT NULL,
    body        VARCHAR(500),
    link        VARCHAR(500),
    is_read     BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- indexes
CREATE INDEX IF NOT EXISTS ix_reports_reporter_id ON reports(reporter_id);
CREATE INDEX IF NOT EXISTS ix_reports_book_id     ON reports(book_id);
CREATE INDEX IF NOT EXISTS ix_reports_is_resolved ON reports(is_resolved);
CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS ix_notif_user_unread   ON notifications(user_id, is_read);

-- follows table
CREATE TABLE IF NOT EXISTS follows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, following_id)
);

-- book_subscriptions table
CREATE TABLE IF NOT EXISTS book_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, book_id)
);

-- Add missing updated_at columns to follows and book_subscriptions if they exist without them
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='follows' AND column_name='updated_at'
    ) THEN
        ALTER TABLE follows ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='book_subscriptions' AND column_name='updated_at'
    ) THEN
        ALTER TABLE book_subscriptions ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
    END IF;
END $$;
