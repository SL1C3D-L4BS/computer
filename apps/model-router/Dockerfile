FROM python:3.14-slim
RUN pip install uv
WORKDIR /app
COPY pyproject.toml .
RUN uv sync --frozen --no-dev
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8020
CMD ["uv", "run", "uvicorn", "model_router.main:app", "--host", "0.0.0.0", "--port", "8020"]
