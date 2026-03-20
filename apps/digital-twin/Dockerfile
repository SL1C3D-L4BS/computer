FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY digital_twin/ digital_twin/

RUN uv sync --frozen --no-dev

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "digital_twin.main:app", "--host", "0.0.0.0", "--port", "8001"]
