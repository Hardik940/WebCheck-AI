FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    QA_AGENT_JOB_POOL_SIZE=2 \
    QA_AGENT_RATE_LIMIT=3.0

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY qa_agent ./qa_agent

RUN pip install --upgrade pip && \
    pip install ".[web]" gunicorn && \
    playwright install --with-deps chromium && \
    mkdir -p /app/qa-agent-output

EXPOSE 5000

CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:${PORT:-5000} qa_agent.web.server:app"]
