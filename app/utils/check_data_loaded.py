"""
app/utils/check_data_loaded.py
──────────────────────────────
Single source of truth for "has the DB been seeded?".

Used two ways:
  1. From entrypoint.sh as a subprocess:
       python app/utils/check_data_loaded.py
       exit 0 → already seeded   (skip seed scripts)
       exit 1 → not yet seeded   (run seed scripts)

  2. Imported by seed scripts:
       from app.utils.check_data_loaded import is_data_seeded, mark_data_seeded
"""

from __future__ import annotations

import asyncio
import os
import sys

# Make sure the project root is on sys.path when run as a script
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))   # …/final_4.1.6
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import text
from app.db.base import engine, AsyncSessionLocal

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def is_data_seeded() -> bool:
    """
    Return True when the database has already been fully seeded.

    Checks the `app_state` table (created by migration 0010) for the
    key 'data_seeded' with value 'true'.  Returns False on any DB error
    so the seed scripts will always run when something is uncertain.
    """
    try:
        async with engine.connect() as conn:
            # 1. Does the table exist yet?
            table_exists: bool = bool(
                (await conn.execute(text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_schema = 'public'"
                    "    AND table_name   = 'app_state'"
                    ")"
                ))).scalar()
            )
            if not table_exists:
                return False

            # 2. Is the seed flag set?
            row = (await conn.execute(text(
                "SELECT value FROM app_state WHERE key = 'data_seeded'"
            ))).fetchone()

            return row is not None and row[0] == "true"

    except Exception as exc:
        print(f"[check_data_loaded] DB check failed: {exc}", file=sys.stderr)
        return False   # treat unknown state as "not seeded"


async def mark_data_seeded() -> None:
    """
    Write (or update) the 'data_seeded' flag in app_state.
    Call this at the end of a successful seed run.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO app_state (key, value, created_at)
            VALUES ('data_seeded', 'true', NOW())
            ON CONFLICT (key) DO UPDATE
                SET value      = 'true',
                    created_at = NOW()
        """))
        await db.commit()
    print("[check_data_loaded] ✓ Marked as seeded in app_state.")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone usage from entrypoint.sh
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    seeded = asyncio.run(is_data_seeded())
    if seeded:
        print("[check_data_loaded] ✓ Database already seeded — skipping.")
        sys.exit(0)   # entrypoint.sh: `if python ... ; then` → branch "skip"
    else:
        print("[check_data_loaded] ○ Database not yet seeded — will run seed scripts.")
        sys.exit(1)   # entrypoint.sh: else branch → run seeds
