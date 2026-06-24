# ORBIT — Operational Response, Briefing & Incident Triage
# Container for any host that runs Docker (Google Cloud Run, Hugging Face Spaces,
# Render, Fly.io, Railway…). Honours the $PORT the platform provides.
FROM python:3.12-slim

WORKDIR /app

# system certs for outbound HTTPS to the live data feeds
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY run.py .

ENV PORT=8000
EXPOSE 8000

# Cloud Run / Render / Fly set $PORT; HF Spaces uses 7860 (set via app_port).
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
