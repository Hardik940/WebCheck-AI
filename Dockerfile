FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    QA_AGENT_JOB_POOL_SIZE=2 \
    QA_AGENT_RATE_LIMIT=3.0

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY qa_agent ./qa_agent

RUN python3 -m pip install --no-cache-dir ".[web]" "playwright==1.65.2" gunicorn
RUN mkdir -p /app/qa-agent-output

EXPOSE 5000

CMD ["sh", "-c", "exec python3 -m gunicorn --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:${PORT:-5000} qa_agent.web.server:app"]
