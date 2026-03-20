FROM python:3.14-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -e .
COPY eval_runner/ ./eval_runner/
EXPOSE 8064
CMD ["uvicorn", "eval_runner.main:app", "--host", "0.0.0.0", "--port", "8064"]
