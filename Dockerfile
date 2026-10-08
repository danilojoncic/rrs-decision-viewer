# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements-runtime.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-compile -r requirements-runtime.txt \
    && find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name "*.pyc" -delete \
    && rm -rf /opt/venv/bin/pip* /opt/venv/lib/python*/site-packages/pip*

FROM python:3.12-slim AS runtime

ENV CASEBOOK_DATA_PATH=/app/data/casebook/world_sailing_cases.json \
    DECISIONS_IMPORT_DIR=/app/data/imports \
    DECISIONS_JSON_DIR=/app/data/decisions \
    PATH=/opt/venv/bin:$PATH \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RRS_RULES_JSON_PATH=/app/data/rules/rules.json \
    WEB_CONCURRENCY=1 \
    WORDING_XLSX_PATH=/app/data/wording/wording.xlsx

WORKDIR /app

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data/imports

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY data ./data

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/healthz', timeout=2).read(1)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --loop uvloop --http httptools --workers ${WEB_CONCURRENCY:-1}"]
