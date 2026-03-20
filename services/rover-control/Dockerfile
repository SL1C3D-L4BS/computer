FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY rover_control/ ./rover_control/

EXPOSE 8040

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "rover_control.main:app", "--host", "0.0.0.0", "--port", "8040"]
