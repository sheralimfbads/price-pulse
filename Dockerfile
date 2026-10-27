
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider" \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY app/ ./app/
COPY sql/ ./sql/
COPY pytest.ini ./pytest.ini

CMD ["python", "scripts/run_pipeline.py"]
