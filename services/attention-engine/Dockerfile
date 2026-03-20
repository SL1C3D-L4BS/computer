FROM python:3.14-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -e .
COPY attention_engine/ ./attention_engine/
EXPOSE 8062
CMD ["uvicorn", "attention_engine.main:app", "--host", "0.0.0.0", "--port", "8062"]
