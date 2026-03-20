FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY control_api/ control_api/

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "control_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
