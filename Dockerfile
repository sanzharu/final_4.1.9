FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Create runtime directories that must exist before the app starts
RUN mkdir -p app/static/uploads/avatars uploads

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Make entrypoint executable (in case git didn't preserve the bit)
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Liveness probe — hits the /health endpoint added in main.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# entrypoint.sh: waits for DB, runs alembic migrations, seeds once, then starts uvicorn
ENTRYPOINT ["bash", "entrypoint.sh"]
