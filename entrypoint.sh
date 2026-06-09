#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — Literary Haven container startup script
#
# Order of operations on every container start:
#   1. Wait until PostgreSQL is ready  (extra safety on top of healthcheck)
#   2. Run Alembic migrations          (idempotent — safe to repeat)
#   3. Check app_state.data_seeded     (via app/utils/check_data_loaded.py)
#      → if NOT seeded  : run seed_real_books.py  (first deploy only)
#      → if already done: skip                    (all subsequent restarts)
#   4. Start the Uvicorn application server
# =============================================================================

set -euo pipefail

# ─── Colour helpers ───────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"
info()    { echo -e "${GREEN}[entrypoint]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[entrypoint]${RESET} $*"; }
fatal()   { echo -e "${RED}[entrypoint] FATAL:${RESET} $*" >&2; exit 1; }

# ─── 1. Wait for PostgreSQL ────────────────────────────────────────────────────
# The healthcheck in docker-compose.yml already gates container startup,
# but we add a belt-and-suspenders loop for SpaceWeb bare-VPS deployments
# where there is no Compose orchestrator.

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
MAX_TRIES=30
WAIT_SEC=2

info "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} …"
for i in $(seq 1 $MAX_TRIES); do
    if python - <<'PYCHECK' 2>/dev/null
import asyncio, os, sys
async def ping():
    import asyncpg
    url = os.environ.get("DATABASE_URL", "")
    # asyncpg uses postgresql:// not postgresql+asyncpg://
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url, timeout=4)
    await conn.close()
asyncio.run(ping())
PYCHECK
    then
        info "PostgreSQL is ready."
        break
    fi
    if [ "$i" -eq "$MAX_TRIES" ]; then
        fatal "PostgreSQL not reachable after $((MAX_TRIES * WAIT_SEC))s — aborting."
    fi
    warn "  … attempt ${i}/${MAX_TRIES}, retrying in ${WAIT_SEC}s"
    sleep "$WAIT_SEC"
done

# ─── 2. Alembic migrations ────────────────────────────────────────────────────
# `alembic upgrade head` is fully idempotent: it compares the current DB
# revision to the latest migration and only runs what is missing.

info "Running Alembic migrations …"
alembic upgrade head
info "Migrations OK."

# ─── 3. One-time data seeding ─────────────────────────────────────────────────
# check_data_loaded.py exits 0 if already seeded, 1 if not.
# `|| true` is intentional — we branch on the exit code ourselves.

info "Checking seed status …"
if python app/utils/check_data_loaded.py; then
    # exit 0 → data already loaded
    info "Data already seeded — skipping seed scripts."
else
    # exit 1 → first-time deployment
    warn "First deployment detected — running seed_real_books.py …"
    warn "This may take several minutes for large datasets."

    python scripts/seed_real_books.py
    SEED_EXIT=$?

    if [ "$SEED_EXIT" -ne 0 ]; then
        fatal "seed_real_books.py exited with code ${SEED_EXIT}."
    fi
    info "Seeding complete."
fi

# ─── 4. Start application ─────────────────────────────────────────────────────
WORKERS="${UVICORN_WORKERS:-2}"
info "Starting Uvicorn with ${WORKERS} worker(s) …"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    --proxy-headers \
    --forwarded-allow-ips='*'
