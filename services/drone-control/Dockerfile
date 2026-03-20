FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY drone_control/ ./drone_control/

EXPOSE 8041

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "drone_control.main:app", "--host", "0.0.0.0", "--port", "8041"]
