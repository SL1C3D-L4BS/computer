FROM python:3.14-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -e .
COPY authz_service/ ./authz_service/
EXPOSE 8060
CMD ["uvicorn", "authz_service.main:app", "--host", "0.0.0.0", "--port", "8060"]
