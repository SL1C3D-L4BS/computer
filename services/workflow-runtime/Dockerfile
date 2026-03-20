FROM python:3.14-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -e .
COPY workflow_runtime/ ./workflow_runtime/
EXPOSE 8050
CMD ["uvicorn", "workflow_runtime.main:app", "--host", "0.0.0.0", "--port", "8050"]
