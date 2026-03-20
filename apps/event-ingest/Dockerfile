FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY event_ingest/ event_ingest/

RUN uv sync --frozen --no-dev

EXPOSE 8003

CMD ["uv", "run", "uvicorn", "event_ingest.main:app", "--host", "0.0.0.0", "--port", "8003"]
