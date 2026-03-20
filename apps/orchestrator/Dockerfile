FROM python:3.14-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY orchestrator/ orchestrator/

# Install dependencies
RUN uv sync --frozen --no-dev

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8002"]
