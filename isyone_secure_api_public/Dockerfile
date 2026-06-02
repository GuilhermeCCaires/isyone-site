FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ISY_DATA_DIR=/app/data \
    ISY_SCRIPTS_DIR=/app/scripts

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/scripts \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 app:app
