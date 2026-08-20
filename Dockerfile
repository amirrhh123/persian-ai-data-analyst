FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
COPY docker_wheels/torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl /tmp/wheels/
ENV PIP_DEFAULT_TIMEOUT=300 PIP_RETRIES=10
RUN pip install --no-cache-dir /tmp/wheels/torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
    && pip install --no-cache-dir --retries 10 --timeout 300 -r requirements.txt \
    && rm -rf /tmp/wheels

COPY backend ./backend
COPY knowledge ./knowledge
COPY schema ./schema

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
