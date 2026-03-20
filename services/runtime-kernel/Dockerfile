FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY runtime_kernel/ ./runtime_kernel/
COPY ../../packages/runtime-contracts/models.py ./models.py

EXPOSE 8063

CMD ["uvicorn", "runtime_kernel.main:app", "--host", "0.0.0.0", "--port", "8063"]
